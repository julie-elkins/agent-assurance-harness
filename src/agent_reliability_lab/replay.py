"""Strict replay of identifier-only adapter runs.

Design rules:

1. Replay files contain the existing AdapterRun protocol, never raw transcripts or
   provider payloads.
2. The file must cover exactly the built-in scenario-pack set; missing coverage is a
   refusal rather than a clean report.
3. Parsing, duplicate detection, agent identity, and scenario identity are checked before
   any finding is evaluated.
4. Replay findings reuse the same scenario evaluators as live adapter runs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .external import ProtocolDecodeError, adapter_run_from_dict
from .models import AgentReport, Finding, FindingStatus
from .packs import (
    build_environment_from_pack,
    load_builtin_packs,
    request_from_pack,
)
from .protocol import AdapterRun, AgentAdapter
from .scenarios import scenarios


REPLAY_VERSION = 1
HARNESS_COMPONENTS = (
    "system_prompt",
    "guardrails",
    "memory",
    "tool_guidance",
    "subagents",
    "skills",
    "scripts",
    "plugins",
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")


@dataclass(frozen=True)
class ReplayRefusal:
    """A structured refusal for an invalid or incomplete replay file."""

    error: str
    message: str
    guidance: str
    source: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe refusal."""

        return {
            "error": self.error,
            "message": self.message,
            "guidance": self.guidance,
            "source": self.source,
        }


@dataclass(frozen=True)
class ReplayCase:
    """One named scenario and its identifier-only adapter response."""

    scenario_id: str
    response: AdapterRun


@dataclass(frozen=True)
class HarnessChangeManifest:
    """Identifier-only metadata describing the harness under evaluation."""

    change_id: str
    components: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the safe manifest shape without prompts or configuration text."""

        return {
            "change_id": self.change_id,
            "components": list(self.components),
        }


@dataclass(frozen=True)
class ReplayFile:
    """A versioned collection of responses from one synthetic agent."""

    replay_version: int
    agent_id: str
    cases: tuple[ReplayCase, ...]
    harness_change: HarnessChangeManifest | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the strict JSON shape used by replay files."""

        from .external import adapter_run_to_dict

        result: dict[str, object] = {
            "replay_version": self.replay_version,
            "agent_id": self.agent_id,
            "runs": [
                {
                    "scenario_id": case.scenario_id,
                    "response": adapter_run_to_dict(case.response),
                }
                for case in self.cases
            ],
        }
        if self.harness_change is not None:
            result["harness_change"] = self.harness_change.to_dict()
        return result


@dataclass(frozen=True)
class ReplayLoadResult:
    """Exactly one parsed replay file or one structured refusal."""

    replay: ReplayFile | None = None
    refusal: ReplayRefusal | None = None


@dataclass(frozen=True)
class ReplayReport:
    """The evaluated result of one complete replay file."""

    source: str
    replay_version: int
    expected_scenario_count: int
    agent_report: AgentReport | None = None
    refusal: ReplayRefusal | None = None

    @property
    def failed(self) -> bool:
        """Return whether the replay must fail a CI gate."""

        if self.refusal is not None or self.agent_report is None:
            return True
        return not self.agent_report.passed

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe report without raw tool payloads."""

        return {
            "source": self.source,
            "replay_version": self.replay_version,
            "expected_scenario_count": self.expected_scenario_count,
            "agent": (
                self.agent_report.to_dict()
                if self.agent_report is not None
                else None
            ),
            "refusal": (
                self.refusal.to_dict() if self.refusal is not None else None
            ),
            "diagnostics": {
                "source": self.source,
                "freshness": "Read once from the caller-supplied local replay file.",
                "warnings": [
                    "Replay evaluates synthetic identifier-only traces; it does not reproduce hidden reasoning or raw tool payloads."
                ],
                "what_it_does_not_show": (
                    "It does not show live-provider behaviour or prove that an agent "
                    "would emit the same trace in a different environment."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Return a reviewable replay summary."""

        if self.refusal is not None:
            return (
                "# Trace Replay\n\n"
                f"**REFUSED** `{self.refusal.error}`: {self.refusal.message}\n\n"
                f"Guidance: {self.refusal.guidance}"
            )
        assert self.agent_report is not None
        outcome = "PASS" if self.agent_report.passed else "FINDINGS"
        lines = [
            "# Trace Replay",
            "",
            f"Agent: `{self.agent_report.agent_id}`",
            f"Scenarios checked: {len(self.agent_report.findings)} "
            f"/ {self.expected_scenario_count}",
            f"Overall result: **{outcome}**",
            "",
        ]
        for finding in self.agent_report.findings:
            lines.append(
                f"- `{finding.status.value}` `{finding.check_id}`: {finding.message}"
            )
        return "\n".join(lines)


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object.")
    return value


def _keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields.")


def _required_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string.")
    return value


def _identifier(value: object, context: str) -> str:
    result = _required_string(value, context)
    if _IDENTIFIER.fullmatch(result) is None:
        raise ValueError(f"{context} must contain identifier characters only.")
    return result


def _parse_harness_change(value: object) -> HarnessChangeManifest:
    data = _object(value, "harness_change")
    _keys(data, {"change_id", "components"}, "harness_change")
    change_id = _identifier(data.get("change_id"), "harness_change.change_id")
    raw_components = data.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ValueError(
            "harness_change.components must be a non-empty list."
        )
    components = []
    seen: set[str] = set()
    for index, component in enumerate(raw_components):
        component_id = _identifier(
            component,
            f"harness_change.components[{index}]",
        )
        if component_id not in HARNESS_COMPONENTS:
            raise ValueError(
                f"harness_change.components[{index}] is not a supported component."
            )
        if component_id in seen:
            raise ValueError(
                f"harness_change.components contains duplicate component {component_id}."
            )
        seen.add(component_id)
        components.append(component_id)
    return HarnessChangeManifest(
        change_id=change_id,
        components=tuple(components),
    )


def _parse_replay(value: object) -> ReplayFile:
    data = _object(value, "replay")
    _keys(
        data,
        {"replay_version", "agent_id", "runs", "harness_change"},
        "replay",
    )
    if data.get("replay_version") != REPLAY_VERSION:
        raise ValueError("replay_version is not supported.")
    agent_id = _required_string(data.get("agent_id"), "agent_id")
    raw_runs = data.get("runs")
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("runs must be a non-empty list.")
    harness_change = (
        _parse_harness_change(data["harness_change"])
        if "harness_change" in data
        else None
    )

    cases = []
    seen_ids: set[str] = set()
    for index, raw_run in enumerate(raw_runs):
        run_data = _object(raw_run, f"runs[{index}]")
        _keys(run_data, {"scenario_id", "response"}, f"runs[{index}]")
        scenario_id = _required_string(
            run_data.get("scenario_id"),
            f"runs[{index}].scenario_id",
        )
        if scenario_id in seen_ids:
            raise ValueError(
                f"runs contains duplicate scenario_id {scenario_id}."
            )
        seen_ids.add(scenario_id)
        try:
            response = adapter_run_from_dict(run_data.get("response"))
        except (ProtocolDecodeError, ValueError) as error:
            raise ValueError(
                f"runs[{index}].response is not a valid AdapterRun: {error}"
            ) from error
        if response.trace is not None:
            if response.trace.scenario_id != scenario_id:
                raise ValueError(
                    f"runs[{index}].response.trace.scenario_id does not match scenario_id."
                )
            if response.trace.agent_id != agent_id:
                raise ValueError(
                    f"runs[{index}].response.trace.agent_id does not match agent_id."
                )
        cases.append(ReplayCase(scenario_id=scenario_id, response=response))
    return ReplayFile(
        replay_version=REPLAY_VERSION,
        agent_id=agent_id,
        cases=tuple(cases),
        harness_change=harness_change,
    )


def load_replay_file(path: Path) -> ReplayLoadResult:
    """Read and strictly validate one local JSON replay file."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return ReplayLoadResult(replay=_parse_replay(value))
    except (OSError, json.JSONDecodeError):
        return ReplayLoadResult(
            refusal=ReplayRefusal(
                error="unreadable_replay_file",
                message="The replay file could not be read as UTF-8 JSON.",
                guidance="Supply one JSON object using replay_version, agent_id, and runs.",
                source=str(path),
            )
        )
    except ValueError as error:
        return ReplayLoadResult(
            refusal=ReplayRefusal(
                error="invalid_replay_file",
                message=str(error),
                guidance="Correct the named replay field and validate it before running CI.",
                source=str(path),
            )
        )


def _refused_finding(pack, message: str) -> Finding:
    required = tuple(item.requirement_id for item in pack.requirements)
    return Finding(
        check_id="replay-run",
        status=FindingStatus.REFUSED,
        message=message,
        dimension=pack.dimension,
        required_evidence=required,
        missing_evidence=required,
        does_not_show="It does not show agent behaviour because the replay response was refused.",
    )


def run_adapter_replay(
    adapter: AgentAdapter,
    *,
    harness_change: HarnessChangeManifest,
) -> ReplayFile:
    """Run one adapter across the built-in packs and keep the replay in memory."""

    cases = tuple(
        ReplayCase(
            scenario_id=pack.scenario_id,
            response=adapter.run(
                request_from_pack(pack),
                environment=build_environment_from_pack(pack),
            ),
        )
        for pack in load_builtin_packs()
    )
    return ReplayFile(
        replay_version=REPLAY_VERSION,
        agent_id=adapter.agent_id,
        cases=cases,
        harness_change=harness_change,
    )


def run_replay_file(path: Path) -> ReplayReport:
    """Evaluate one complete replay file against the built-in packs."""

    loaded = load_replay_file(path)
    if loaded.refusal is not None:
        return ReplayReport(
            source=str(path),
            replay_version=REPLAY_VERSION,
            expected_scenario_count=0,
            refusal=loaded.refusal,
        )
    assert loaded.replay is not None
    return run_replay(loaded.replay, source=str(path))


def run_replay(replay: ReplayFile, *, source: str) -> ReplayReport:
    """Evaluate an already-normalized replay without writing it to disk."""

    try:
        packs = load_builtin_packs()
    except RuntimeError as error:
        return ReplayReport(
            source=source,
            replay_version=replay.replay_version,
            expected_scenario_count=0,
            refusal=ReplayRefusal(
                error="scenario_registry_refused",
                message="The built-in scenario packs are not valid.",
                guidance="Repair the pack validation defect before replaying traces.",
                source=str(error),
            ),
        )
    pack_by_id = {pack.scenario_id: pack for pack in packs}
    actual_ids = {case.scenario_id for case in replay.cases}
    expected_ids = set(pack_by_id)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing scenario IDs: {', '.join(missing)}")
        if extra:
            details.append(f"unknown scenario IDs: {', '.join(extra)}")
        return ReplayReport(
            source=source,
            replay_version=replay.replay_version,
            expected_scenario_count=len(expected_ids),
            refusal=ReplayRefusal(
                error="incomplete_replay_coverage",
                message="The replay file does not cover exactly the built-in scenario set: "
                + "; ".join(details)
                + ".",
                guidance="Replay one response for every listed scenario_id and no others.",
                source=source,
            ),
        )

    scenarios_by_id = {scenario.scenario_id: scenario for scenario in scenarios()}
    missing_controls = sorted(expected_ids - set(scenarios_by_id))
    if missing_controls:
        return ReplayReport(
            source=source,
            replay_version=replay.replay_version,
            expected_scenario_count=len(expected_ids),
            refusal=ReplayRefusal(
                error="reference_scenario_missing",
                message=(
                    "The built-in pack set has no Python parity control for: "
                    + ", ".join(missing_controls)
                    + "."
                ),
                guidance="Restore the matching reference scenario before replaying traces.",
                source=source,
            ),
        )
    findings = []
    trace_counts: dict[str, int] = {}
    for case in replay.cases:
        pack = pack_by_id[case.scenario_id]
        response = case.response
        if response.refusal is not None:
            findings.append(_refused_finding(pack, response.refusal.message))
            trace_counts[case.scenario_id] = 0
            continue
        assert response.trace is not None
        scenario = scenarios_by_id[case.scenario_id]
        trace_counts[case.scenario_id] = len(response.trace.tool_calls)
        findings.append(scenario.evaluate(response.trace, pack.contract))
    return ReplayReport(
        source=source,
        replay_version=replay.replay_version,
        expected_scenario_count=len(expected_ids),
        agent_report=AgentReport(
            agent_id=replay.agent_id,
            findings=tuple(findings),
            trace_counts=trace_counts,
        ),
    )
