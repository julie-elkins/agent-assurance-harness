"""Deterministic launch-to-field enablement pack assurance.

The launch-to-field pack is a small, metadata-only reference workflow for turning a
new technical capability into a demo, hands-on lab, and quick-reference guide.  It
reuses the existing bounded content pipeline instead of creating a second evidence
evaluator.

The public fixture describes identifiers and synthetic source bytes only.  The report
does not contain lesson text, prompts, provider output, credentials, or source paths.
Approval means the pack is ready for human approval; it is not publication authority.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum

from .content_pipeline import (
    ContentPipelineRequest,
    PipelineClaim,
    PipelineDecision,
    PipelineFindingLocator,
    run_content_assurance_pipeline,
)


ENABLEMENT_PACK_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_ASSET_TYPES = frozenset({"demo", "lab", "quick_reference"})


class EnablementDecision(str, Enum):
    """The safe publication-preparation outcome for one enablement pack."""

    READY_FOR_HUMAN_APPROVAL = "ready_for_human_approval"
    BLOCKED = "blocked"
    REFUSED = "refused"


@dataclass(frozen=True)
class EnablementAsset:
    """One teachable asset represented by safe identifiers."""

    asset_id: str
    asset_type: str
    audience_id: str
    claim_id: str
    section_id: str
    support_status: str = "supported"


@dataclass(frozen=True)
class FeedbackSignal:
    """A synthetic usage or learner signal without free-form feedback text."""

    signal_id: str
    asset_id: str
    signal_type: str
    count: int
    recommended_action: str


@dataclass(frozen=True)
class LaunchToFieldPackRequest:
    """One bounded pack review request."""

    pack_id: str
    revision: str
    source_id: str
    source_url: str
    source_bytes: bytes
    age_seconds: float | None
    approved_source_ids: tuple[str, ...]
    max_age_seconds: float
    assets: tuple[EnablementAsset, ...]
    feedback: tuple[FeedbackSignal, ...]


@dataclass(frozen=True)
class LaunchToFieldPackReport:
    """Metadata-only result for one launch-to-field pack."""

    pack_id: str
    revision: str
    decision: EnablementDecision
    pack_digest: str
    asset_ids: tuple[str, ...]
    asset_types: tuple[str, ...]
    audience_ids: tuple[str, ...]
    source_id: str
    source_digest: str | None
    feedback_signal_ids: tuple[str, ...]
    feedback_signal_count: int
    finding_locators: tuple[PipelineFindingLocator, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    refusal_code: str | None = None

    @property
    def passed(self) -> bool:
        """Return true only when the pack is ready for human approval."""

        return self.decision is EnablementDecision.READY_FOR_HUMAN_APPROVAL

    def to_dict(self) -> dict[str, object]:
        """Return the safe report representation."""

        return {
            "enablement_pack_version": ENABLEMENT_PACK_VERSION,
            "pack_id": self.pack_id,
            "revision": self.revision,
            "decision": self.decision.value,
            "passed": self.passed,
            "pack_digest": self.pack_digest,
            "asset_ids": list(self.asset_ids),
            "asset_types": list(self.asset_types),
            "audience_ids": list(self.audience_ids),
            "source_id": self.source_id,
            "source_digest": self.source_digest,
            "feedback_signal_ids": list(self.feedback_signal_ids),
            "feedback_signal_count": self.feedback_signal_count,
            "finding_locators": [
                locator.to_dict() for locator in self.finding_locators
            ],
            "blocked_reasons": list(self.blocked_reasons),
            "refusal_code": self.refusal_code,
            "diagnostics": {
                "warnings": [
                    "This report contains identifiers, states, counts, and hashes only.",
                    "A ready pack still requires human approval before publication.",
                ],
                "what_it_does_not_show": (
                    "It does not prove that the demo teaches effectively, that a "
                    "source is semantically complete, or that a live provider behaves "
                    "like the synthetic fixture."
                ),
            },
        }


@dataclass(frozen=True)
class EnablementPackCase:
    """A deterministic positive or degraded pack case."""

    case_id: str
    request: LaunchToFieldPackRequest
    expected_decision: EnablementDecision
    expected_reason: str | None = None


@dataclass(frozen=True)
class EnablementPackSuiteReport:
    """The ready path and deliberate launch-to-field controls."""

    reports: tuple[tuple[str, LaunchToFieldPackReport], ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return true only when every declared control behaves as expected."""

        return not self.controls_missed

    def to_dict(self) -> dict[str, object]:
        """Return metadata-only suite output."""

        return {
            "enablement_pack_version": ENABLEMENT_PACK_VERSION,
            "passed": self.passed,
            "cases": [
                {
                    "case_id": case_id,
                    **report.to_dict(),
                }
                for case_id, report in self.reports
            ],
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "diagnostics": {
                "warnings": [
                    "The suite uses synthetic launch assets and source metadata.",
                    "The blocked cases are negative controls, not production findings.",
                ],
                "what_it_does_not_show": (
                    "It does not establish semantic truth, live-model quality, "
                    "learner success, or automatic publication authority."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a short reviewer-facing summary."""

        lines = [
            "# Launch-to-Field Enablement Pack Report",
            "",
            f"Decision: {'PASS' if self.passed else 'BLOCKED'}",
            "",
            "| Case | Decision | Assets | Audiences | Reasons |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for case_id, report in self.reports:
            reasons = ", ".join(report.blocked_reasons)
            if not reasons and report.refusal_code is not None:
                reasons = report.refusal_code
            reasons = reasons or "none"
            lines.append(
                f"| `{case_id}` | `{report.decision.value}` | "
                f"`{len(report.asset_ids)}` | `{len(report.audience_ids)}` | "
                f"{reasons} |"
            )
        lines.extend(
            [
                "",
                "Controls caught: "
                + (", ".join(f"`{item}`" for item in self.controls_caught) or "none"),
                "",
                "Controls missed: "
                + (", ".join(f"`{item}`" for item in self.controls_missed) or "none"),
                "",
                "This report contains identifiers, counts, and hashes only.",
                "A ready pack still requires human approval before publication.",
                "",
            ]
        )
        return "\n".join(lines)


def run_launch_to_field_pack(
    request: LaunchToFieldPackRequest,
) -> LaunchToFieldPackReport:
    """Review one launch pack through the existing content assurance boundary."""

    pack_digest = _pack_digest(request)
    refusal = _validate_pack(request)
    if refusal is not None:
        return LaunchToFieldPackReport(
            pack_id=request.pack_id,
            revision=request.revision,
            decision=EnablementDecision.REFUSED,
            pack_digest=pack_digest,
            asset_ids=tuple(asset.asset_id for asset in request.assets),
            asset_types=tuple(asset.asset_type for asset in request.assets),
            audience_ids=_unique(
                asset.audience_id for asset in request.assets
            ),
            source_id=request.source_id,
            source_digest=None,
            feedback_signal_ids=tuple(
                signal.signal_id for signal in request.feedback
            ),
            feedback_signal_count=len(request.feedback),
            refusal_code=refusal,
        )

    pipeline_request = ContentPipelineRequest(
        case_id=f"launch-pack:{request.pack_id}",
        artifact_id=f"pack:{request.pack_id}",
        artifact_revision=request.revision,
        artifact_digest=pack_digest,
        reuse_key=f"launch-to-field:{request.pack_id}",
        source_id=request.source_id,
        authority="public-reference-docs",
        source_url=request.source_url,
        source_bytes=request.source_bytes,
        age_seconds=request.age_seconds,
        claims=tuple(
            PipelineClaim(
                claim_id=asset.claim_id,
                section_id=asset.section_id,
                support_status=asset.support_status,
            )
            for asset in request.assets
        ),
        approved_source_ids=request.approved_source_ids,
        max_age_seconds=request.max_age_seconds,
    )
    pipeline = run_content_assurance_pipeline(pipeline_request)
    decision = (
        EnablementDecision.READY_FOR_HUMAN_APPROVAL
        if pipeline.decision is PipelineDecision.APPROVED
        else EnablementDecision.BLOCKED
    )
    return LaunchToFieldPackReport(
        pack_id=request.pack_id,
        revision=request.revision,
        decision=decision,
        pack_digest=pack_digest,
        asset_ids=tuple(asset.asset_id for asset in request.assets),
        asset_types=tuple(asset.asset_type for asset in request.assets),
        audience_ids=_unique(asset.audience_id for asset in request.assets),
        source_id=request.source_id,
        source_digest=pipeline.source_digest,
        feedback_signal_ids=tuple(
            signal.signal_id for signal in request.feedback
        ),
        feedback_signal_count=len(request.feedback),
        finding_locators=pipeline.finding_locators,
        blocked_reasons=(
            pipeline.abstention_reasons
            if pipeline.decision is not PipelineDecision.APPROVED
            else ()
        ),
        refusal_code=pipeline.refusal_code,
    )


def reference_launch_to_field_cases() -> tuple[EnablementPackCase, ...]:
    """Return the public synthetic ready path and degraded controls."""

    source_bytes = (
        b"<html><body><h1>Synthetic platform capability</h1>"
        b"<p>Approved launch guidance fixture.</p></body></html>"
    )
    assets = (
        EnablementAsset(
            asset_id="asset-platform-demo",
            asset_type="demo",
            audience_id="audience-technical-seller",
            claim_id="claim-platform-demo",
            section_id="section-platform-demo",
        ),
        EnablementAsset(
            asset_id="asset-platform-lab",
            asset_type="lab",
            audience_id="audience-technical-seller",
            claim_id="claim-platform-lab",
            section_id="section-platform-lab",
        ),
        EnablementAsset(
            asset_id="asset-platform-quick-reference",
            asset_type="quick_reference",
            audience_id="audience-technical-seller",
            claim_id="claim-platform-quick-reference",
            section_id="section-platform-quick-reference",
        ),
    )
    feedback = (
        FeedbackSignal(
            signal_id="feedback-lab-completion",
            asset_id="asset-platform-lab",
            signal_type="completion_rate",
            count=18,
            recommended_action="retain",
        ),
        FeedbackSignal(
            signal_id="feedback-demo-question",
            asset_id="asset-platform-demo",
            signal_type="repeated_question",
            count=3,
            recommended_action="clarify",
        ),
    )
    base = {
        "pack_id": "pack-platform-launch",
        "revision": "pack-revision-001",
        "source_id": "source-approved-docs",
        "source_url": "https://docs.anthropic.com/",
        "source_bytes": source_bytes,
        "age_seconds": 300,
        "approved_source_ids": ("source-approved-docs",),
        "max_age_seconds": 3600,
        "assets": assets,
        "feedback": feedback,
    }
    return (
        EnablementPackCase(
            case_id="launch-pack-ready",
            request=LaunchToFieldPackRequest(**base),
            expected_decision=EnablementDecision.READY_FOR_HUMAN_APPROVAL,
        ),
        EnablementPackCase(
            case_id="launch-pack-stale-source",
            request=LaunchToFieldPackRequest(**{**base, "age_seconds": 7200}),
            expected_decision=EnablementDecision.BLOCKED,
            expected_reason="evidence_stale",
        ),
        EnablementPackCase(
            case_id="launch-pack-unsupported-claim",
            request=LaunchToFieldPackRequest(
                **{
                    **base,
                    "assets": (
                        *assets[:2],
                        EnablementAsset(
                            asset_id="asset-platform-quick-reference",
                            asset_type="quick_reference",
                            audience_id="audience-technical-seller",
                            claim_id="claim-platform-quick-reference",
                            section_id="section-platform-quick-reference",
                            support_status="unsupported",
                        ),
                    ),
                }
            ),
            expected_decision=EnablementDecision.BLOCKED,
            expected_reason="claim_unsupported",
        ),
        EnablementPackCase(
            case_id="launch-pack-wrong-source",
            request=LaunchToFieldPackRequest(
                **{
                    **base,
                    "source_id": "source-unapproved-copy",
                    "source_url": "https://developers.openai.com/",
                }
            ),
            expected_decision=EnablementDecision.BLOCKED,
            expected_reason="evidence_wrong_source",
        ),
        EnablementPackCase(
            case_id="launch-pack-incomplete-assets",
            request=LaunchToFieldPackRequest(
                **{**base, "assets": assets[:2]}
            ),
            expected_decision=EnablementDecision.REFUSED,
            expected_reason="missing_asset_type:quick_reference",
        ),
    )


def run_reference_launch_to_field_suite() -> EnablementPackSuiteReport:
    """Run the positive path and verify each launch-pack control."""

    reports: list[tuple[str, LaunchToFieldPackReport]] = []
    caught: list[str] = []
    missed: list[str] = []
    for case in reference_launch_to_field_cases():
        report = run_launch_to_field_pack(case.request)
        reports.append((case.case_id, report))
        expected_decision = report.decision is case.expected_decision
        expected_reason = (
            case.expected_reason is None
            or case.expected_reason in report.blocked_reasons
            or case.expected_reason == report.refusal_code
        )
        if expected_decision and expected_reason:
            caught.append(case.case_id)
        else:
            missed.append(case.case_id)
    return EnablementPackSuiteReport(
        reports=tuple(reports),
        controls_caught=tuple(caught),
        controls_missed=tuple(missed),
    )


def _validate_pack(request: LaunchToFieldPackRequest) -> str | None:
    for value, code in (
        (request.pack_id, "invalid_pack_id"),
        (request.revision, "invalid_revision"),
        (request.source_id, "invalid_source_id"),
    ):
        if not _valid_identifier(value):
            return code
    if not isinstance(request.source_bytes, bytes) or not request.source_bytes:
        return "missing_source_bytes"
    if (
        isinstance(request.max_age_seconds, bool)
        or not isinstance(request.max_age_seconds, (int, float))
        or request.max_age_seconds < 0
    ):
        return "invalid_max_age_seconds"
    if request.age_seconds is not None and (
        isinstance(request.age_seconds, bool)
        or not isinstance(request.age_seconds, (int, float))
        or request.age_seconds < 0
    ):
        return "invalid_source_age"
    if not request.assets:
        return "missing_assets"
    asset_ids = [asset.asset_id for asset in request.assets]
    if len(asset_ids) != len(set(asset_ids)):
        return "duplicate_asset_id"
    claim_ids = [asset.claim_id for asset in request.assets]
    if len(claim_ids) != len(set(claim_ids)):
        return "duplicate_claim_id"
    for asset in request.assets:
        if not _valid_identifier(asset.asset_id):
            return "invalid_asset_id"
        if asset.asset_type not in _ASSET_TYPES:
            return "invalid_asset_type"
        if not _valid_identifier(asset.audience_id):
            return "invalid_audience_id"
        if not _valid_identifier(asset.claim_id):
            return "invalid_claim_id"
        if not _valid_identifier(asset.section_id):
            return "invalid_section_id"
        if asset.support_status not in {
            "supported",
            "unsupported",
            "conflicting",
            "ambiguous",
        }:
            return "invalid_support_status"
    missing_types = sorted(_ASSET_TYPES - {asset.asset_type for asset in request.assets})
    if missing_types:
        return f"missing_asset_type:{missing_types[0]}"
    feedback_ids = [signal.signal_id for signal in request.feedback]
    if len(feedback_ids) != len(set(feedback_ids)):
        return "duplicate_feedback_id"
    known_assets = set(asset_ids)
    for signal in request.feedback:
        if not _valid_identifier(signal.signal_id):
            return "invalid_feedback_id"
        if signal.asset_id not in known_assets:
            return "feedback_asset_missing"
        if not _valid_identifier(signal.signal_type):
            return "invalid_feedback_type"
        if (
            isinstance(signal.count, bool)
            or not isinstance(signal.count, int)
            or signal.count < 0
        ):
            return "invalid_feedback_count"
        if not _valid_identifier(signal.recommended_action):
            return "invalid_feedback_action"
    if not request.feedback:
        return "missing_feedback_signals"
    return None


def _pack_digest(request: LaunchToFieldPackRequest) -> str:
    """Fingerprint pack metadata without retaining or exporting source bytes."""

    fields = [
        request.pack_id,
        request.revision,
        request.source_id,
        *(
            f"{asset.asset_id}:{asset.asset_type}:{asset.audience_id}:"
            f"{asset.claim_id}:{asset.section_id}:{asset.support_status}"
            for asset in request.assets
        ),
        *(
            f"{signal.signal_id}:{signal.asset_id}:{signal.signal_type}:"
            f"{signal.count}:{signal.recommended_action}"
            for signal in request.feedback
        ),
    ]
    return "sha256:" + hashlib.sha256("|".join(fields).encode("utf-8")).hexdigest()


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _unique(values: object) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value not in result:
            result.append(value)
    return tuple(result)
