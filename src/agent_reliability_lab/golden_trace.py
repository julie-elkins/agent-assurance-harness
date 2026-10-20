"""Metadata-only Golden Trace baselines for observable evidence drift.

Design rules:

1. A Golden Trace fingerprints the observable evidence shape, never prompts, raw
   payloads, or free-form claim and answer text.
2. The baseline is valid only when it passes the current evaluator and matches the
   current built-in scenario-pack set.
3. Any changed scenario projection is visible as drift, even when the evaluator still
   passes; this catches silent evidence changes that a status-only comparison can miss.
4. Refusals remain structured results and are never treated as an empty successful trace.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .models import ToolCall, Trace
from .packs import ScenarioPack
from .pack_provenance import pack_set_sha256
from .protocol import AdapterRun
from .replay import ReplayFile, ReplayRefusal, load_replay_file, run_replay


GOLDEN_TRACE_VERSION = 1


@dataclass(frozen=True)
class GoldenTraceManifest:
    """The metadata needed to validate one approved Golden Trace."""

    golden_trace_version: int
    agent_id: str
    scenario_count: int
    pack_set_sha256: str
    trace_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return the metadata-only manifest shape."""

        return {
            "golden_trace_version": self.golden_trace_version,
            "agent_id": self.agent_id,
            "scenario_count": self.scenario_count,
            "pack_set_sha256": self.pack_set_sha256,
            "trace_sha256": self.trace_sha256,
        }


@dataclass(frozen=True)
class GoldenTraceDrift:
    """One scenario whose observable evidence changed from the baseline."""

    scenario_id: str
    golden_sha256: str
    candidate_sha256: str
    changed_components: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return identifiers and hashes without trace content."""

        return {
            "scenario_id": self.scenario_id,
            "golden_sha256": self.golden_sha256,
            "candidate_sha256": self.candidate_sha256,
            "changed_components": list(self.changed_components),
        }


@dataclass(frozen=True)
class GoldenTraceReport:
    """The result of comparing a candidate with the approved Golden Trace."""

    golden_source: str
    candidate_source: str
    manifest: GoldenTraceManifest | None
    golden_trace_sha256: str | None
    candidate_trace_sha256: str | None
    expected_scenario_count: int
    candidate_evaluation_passed: bool | None
    drifts: tuple[GoldenTraceDrift, ...] = ()
    refusal: ReplayRefusal | None = None

    @property
    def passed(self) -> bool:
        """Return whether the candidate matches and passes the Golden Trace gate."""

        return (
            self.refusal is None
            and self.candidate_evaluation_passed is True
            and not self.drifts
        )

    def to_dict(self) -> dict[str, object]:
        """Return hashes, counts, and drift metadata without trace content."""

        return {
            "golden_source": self.golden_source,
            "candidate_source": self.candidate_source,
            "manifest": (
                self.manifest.to_dict() if self.manifest is not None else None
            ),
            "golden_trace_sha256": self.golden_trace_sha256,
            "candidate_trace_sha256": self.candidate_trace_sha256,
            "expected_scenario_count": self.expected_scenario_count,
            "candidate_evaluation_passed": self.candidate_evaluation_passed,
            "passed": self.passed,
            "drifts": [drift.to_dict() for drift in self.drifts],
            "refusal": (
                self.refusal.to_dict() if self.refusal is not None else None
            ),
            "diagnostics": {
                "warnings": [
                    "A Golden Trace detects canonical evidence drift; it does not establish causality or live-model quality.",
                    "The digest excludes free-form claim and answer text so wording changes do not become false safety regressions.",
                ],
                "what_it_does_not_show": (
                    "It does not show why the candidate changed, whether the baseline "
                    "was realistic, or whether an unchanged trace reflects correct "
                    "hidden reasoning."
                ),
            },
        }


def build_golden_manifest(
    replay: ReplayFile,
    packs: tuple[ScenarioPack, ...],
) -> GoldenTraceManifest:
    """Build a manifest from a validated replay and current pack set."""

    if not replay.cases:
        raise ValueError("A Golden Trace requires at least one replay case.")
    return GoldenTraceManifest(
        golden_trace_version=GOLDEN_TRACE_VERSION,
        agent_id=replay.agent_id,
        scenario_count=len(replay.cases),
        pack_set_sha256=pack_set_sha256(packs),
        trace_sha256=golden_trace_sha256(replay),
    )


def load_golden_manifest(path: Path) -> GoldenTraceManifest:
    """Load and strictly validate a metadata-only Golden Trace manifest."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Golden Trace manifest must be an object.")
    allowed = {
        "golden_trace_version",
        "agent_id",
        "scenario_count",
        "pack_set_sha256",
        "trace_sha256",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError("Golden Trace manifest contains unknown fields.")
    if data.get("golden_trace_version") != GOLDEN_TRACE_VERSION:
        raise ValueError("golden_trace_version is not supported.")
    agent_id = data.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("Golden Trace manifest agent_id must be non-empty.")
    scenario_count = data.get("scenario_count")
    if (
        isinstance(scenario_count, bool)
        or not isinstance(scenario_count, int)
        or scenario_count < 1
    ):
        raise ValueError("Golden Trace manifest scenario_count must be positive.")
    pack_hash = data.get("pack_set_sha256")
    trace_hash = data.get("trace_sha256")
    if not _sha256(pack_hash, "pack_set_sha256"):
        raise ValueError("Golden Trace manifest pack_set_sha256 must be SHA-256.")
    if not _sha256(trace_hash, "trace_sha256"):
        raise ValueError("Golden Trace manifest trace_sha256 must be SHA-256.")
    return GoldenTraceManifest(
        golden_trace_version=GOLDEN_TRACE_VERSION,
        agent_id=agent_id,
        scenario_count=scenario_count,
        pack_set_sha256=pack_hash,
        trace_sha256=trace_hash,
    )


def golden_trace_sha256(replay: ReplayFile) -> str:
    """Return the canonical digest of all observable evidence in a replay."""

    return _sha256_json(_replay_projection(replay))


def compare_golden_trace(
    golden: ReplayFile,
    candidate: ReplayFile,
    *,
    manifest: GoldenTraceManifest,
    packs: tuple[ScenarioPack, ...],
    golden_source: str = "golden",
    candidate_source: str = "candidate",
) -> GoldenTraceReport:
    """Compare a candidate replay with a validated Golden Trace baseline."""

    golden_hash = golden_trace_sha256(golden)
    candidate_hash = golden_trace_sha256(candidate)
    if golden.agent_id != manifest.agent_id:
        return _refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            "golden_agent_id_mismatch",
            "The Golden Trace manifest does not identify the replay's agent.",
            "Regenerate the manifest from the approved replay.",
        )
    if len(golden.cases) != manifest.scenario_count:
        return _refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            "golden_scenario_count_mismatch",
            "The Golden Trace manifest does not match the replay coverage.",
            "Regenerate the manifest from a complete approved replay.",
        )
    current_pack_hash = pack_set_sha256(packs)
    if manifest.pack_set_sha256 != current_pack_hash:
        return _refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            "golden_pack_set_mismatch",
            "The Golden Trace was created against a different scenario-pack set.",
            "Review the pack change and regenerate the Golden Trace deliberately.",
        )
    if manifest.trace_sha256 != golden_hash:
        return _refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            "golden_trace_digest_mismatch",
            "The approved replay no longer matches its Golden Trace manifest.",
            "Regenerate the manifest only after reviewing the baseline change.",
        )
    golden_report = run_replay(golden, source=golden_source)
    if golden_report.refusal is not None or golden_report.agent_report is None:
        refusal = golden_report.refusal or ReplayRefusal(
            error="golden_trace_invalid",
            message="The Golden Trace did not produce an evaluable report.",
            guidance="Repair the approved replay before using it as a baseline.",
            source=golden_source,
        )
        return _report_with_refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            refusal,
        )
    if not golden_report.agent_report.passed:
        return _report_with_refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            ReplayRefusal(
                error="golden_trace_not_passing",
                message="The approved Golden Trace contains a failing evaluation.",
                guidance="Repair or replace the baseline before comparing candidates.",
                source=golden_source,
            ),
        )
    if candidate.agent_id != manifest.agent_id:
        return _report_with_refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            ReplayRefusal(
                error="candidate_agent_id_mismatch",
                message="The candidate does not identify the same agent as the Golden Trace.",
                guidance="Compare the same adapter integration against its baseline.",
                source=candidate_source,
            ),
        )
    candidate_report = run_replay(candidate, source=candidate_source)
    if candidate_report.refusal is not None or candidate_report.agent_report is None:
        return _report_with_refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            candidate_report.refusal
            or ReplayRefusal(
                error="candidate_trace_invalid",
                message="The candidate did not produce an evaluable report.",
                guidance="Repair the candidate adapter before comparing its trace.",
                source=candidate_source,
            ),
        )
    golden_cases = {
        case.scenario_id: case for case in golden.cases
    }
    candidate_cases = {
        case.scenario_id: case for case in candidate.cases
    }
    if set(golden_cases) != set(candidate_cases):
        return _report_with_refusal(
            golden_source,
            candidate_source,
            manifest,
            golden_hash,
            candidate_hash,
            manifest.scenario_count,
            ReplayRefusal(
                error="golden_scenario_alignment_failed",
                message="Golden and candidate traces do not cover the same scenarios.",
                guidance="Produce one response for every built-in scenario and no others.",
                source=candidate_source,
            ),
        )
    changed_components = (
        candidate.harness_change.components
        if candidate.harness_change is not None
        else ()
    )
    drifts = []
    for scenario_id in sorted(golden_cases):
        baseline_case_hash = _sha256_json(
            _case_projection(golden_cases[scenario_id].scenario_id, golden_cases[scenario_id].response)
        )
        candidate_case_hash = _sha256_json(
            _case_projection(
                candidate_cases[scenario_id].scenario_id,
                candidate_cases[scenario_id].response,
            )
        )
        if baseline_case_hash != candidate_case_hash:
            drifts.append(
                GoldenTraceDrift(
                    scenario_id=scenario_id,
                    golden_sha256=baseline_case_hash,
                    candidate_sha256=candidate_case_hash,
                    changed_components=changed_components,
                )
            )
    return GoldenTraceReport(
        golden_source=golden_source,
        candidate_source=candidate_source,
        manifest=manifest,
        golden_trace_sha256=golden_hash,
        candidate_trace_sha256=candidate_hash,
        expected_scenario_count=manifest.scenario_count,
        candidate_evaluation_passed=candidate_report.agent_report.passed,
        drifts=tuple(drifts),
    )


def load_replay_for_golden(path: Path) -> ReplayFile:
    """Load an approved replay or raise a bounded validation error."""

    result = load_replay_file(path)
    if result.refusal is not None or result.replay is None:
        message = result.refusal.message if result.refusal else "Replay was empty."
        raise ValueError(message)
    return result.replay


def _replay_projection(replay: ReplayFile) -> dict[str, object]:
    return {
        "replay_version": replay.replay_version,
        "agent_id": replay.agent_id,
        "cases": [
            _case_projection(case.scenario_id, case.response)
            for case in sorted(replay.cases, key=lambda item: item.scenario_id)
        ],
    }


def _case_projection(scenario_id: str, response: AdapterRun) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "trace": (
            _trace_projection(response.trace)
            if response.trace is not None
            else None
        ),
        "refusal_code": (
            response.refusal.error if response.refusal is not None else None
        ),
        "execution_budget": (
            response.execution_budget.to_dict()
            if response.execution_budget is not None
            else None
        ),
    }


def _trace_projection(trace: Trace | None) -> dict[str, object] | None:
    if trace is None:
        return None
    return {
        "scenario_id": trace.scenario_id,
        "agent_id": trace.agent_id,
        "tool_calls": [_tool_call_projection(call) for call in trace.tool_calls],
        "claim_present": trace.claim is not None,
        "answer_present": trace.answer is not None,
        "abstained": trace.abstained,
        "evidence_ids": list(trace.evidence_ids),
        "side_effects": list(trace.side_effects),
        "authorization_ids": list(trace.authorization_ids),
        "authorization_operation_ids": list(trace.authorization_operation_ids),
        "authorization_action_digests": list(trace.authorization_action_digests),
        "tool_output_flags": list(trace.tool_output_flags),
        "operation_ids": list(trace.operation_ids),
        "idempotency_keys": list(trace.idempotency_keys),
        "action_digests": list(trace.action_digests),
        "reconciliation_ids": list(trace.reconciliation_ids),
        "reconciliation_statuses": list(trace.reconciliation_statuses),
    }


def _tool_call_projection(call: ToolCall) -> dict[str, object]:
    return {
        "name": call.name,
        "result_status": call.result_status,
        "result_id": call.result_id,
        "source": call.source,
        "age_seconds": call.age_seconds,
    }


def _sha256_json(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: object, context: str) -> str | None:
    if not isinstance(value, str) or len(value) != 64:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value


def _refusal(
    golden_source: str,
    candidate_source: str,
    manifest: GoldenTraceManifest,
    golden_hash: str,
    candidate_hash: str,
    scenario_count: int,
    error: str,
    message: str,
    guidance: str,
) -> GoldenTraceReport:
    return _report_with_refusal(
        golden_source,
        candidate_source,
        manifest,
        golden_hash,
        candidate_hash,
        scenario_count,
        ReplayRefusal(
            error=error,
            message=message,
            guidance=guidance,
            source=golden_source,
        ),
    )


def _report_with_refusal(
    golden_source: str,
    candidate_source: str,
    manifest: GoldenTraceManifest | None,
    golden_hash: str | None,
    candidate_hash: str | None,
    scenario_count: int,
    refusal: ReplayRefusal,
) -> GoldenTraceReport:
    return GoldenTraceReport(
        golden_source=golden_source,
        candidate_source=candidate_source,
        manifest=manifest,
        golden_trace_sha256=golden_hash,
        candidate_trace_sha256=candidate_hash,
        expected_scenario_count=scenario_count,
        candidate_evaluation_passed=None,
        refusal=refusal,
    )


__all__ = [
    "GOLDEN_TRACE_VERSION",
    "GoldenTraceDrift",
    "GoldenTraceManifest",
    "GoldenTraceReport",
    "build_golden_manifest",
    "compare_golden_trace",
    "golden_trace_sha256",
    "load_golden_manifest",
    "load_replay_for_golden",
]
