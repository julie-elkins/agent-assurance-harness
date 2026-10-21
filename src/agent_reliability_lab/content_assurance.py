"""Deterministic technical-content assurance for the public reference agent.

This module is the first vertical slice of the public content-assurance system. It
checks synthetic lesson claims against an explicit source registry and returns an
approval or abstention decision without carrying lesson text.

The design deliberately separates:

* an input refusal, which means the request itself is malformed;
* an abstention, which means the request is valid but the evidence cannot support
  publication; and
* approval, which means every declared claim passed the declared checks.

It is provider-neutral and deterministic so the same fixture produces the same
decision in a developer terminal and in CI.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from urllib.parse import urlparse

from .models import FindingStatus
from .protocol import AdapterRefusal, AdapterRun, ScenarioRequest
from .recorder import TraceRecorder


CONTENT_ASSURANCE_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_OFFICIAL_DOCUMENTATION_HOSTS = frozenset(
    {
        "docs.aws.amazon.com",
        "docs.anthropic.com",
        "anthropic.com",
        "www.anthropic.com",
        "platform.claude.com",
        "developers.openai.com",
        "platform.openai.com",
    }
)


class ContentDecision(str, Enum):
    """The safe publication decision for one synthetic content artifact."""

    APPROVED = "approved"
    ABSTAIN = "abstain"
    REFUSED = "refused"


@dataclass(frozen=True)
class ContentClaim:
    """One content claim and the source fingerprint expected to support it."""

    claim_id: str
    source_id: str
    expected_source_digest: str


@dataclass(frozen=True)
class ContentArtifact:
    """Metadata for one technical-content artifact under review."""

    artifact_id: str
    revision: str
    content_digest: str
    reuse_key: str
    claims: tuple[ContentClaim, ...]


@dataclass(frozen=True)
class ContentSource:
    """A source-registry record with freshness and authority metadata."""

    source_id: str
    authority: str
    source_url: str
    source_digest: str
    age_seconds: float | None


@dataclass(frozen=True)
class ContentAssuranceRequest:
    """The publication policy applied to one artifact review."""

    artifact_id: str
    approved_source_ids: tuple[str, ...]
    max_age_seconds: float


@dataclass(frozen=True)
class ContentCheck:
    """One metadata-only check performed for one claim."""

    check_id: str
    claim_id: str
    status: FindingStatus
    evidence_id: str | None
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the safe public representation of a check."""

        value: dict[str, object] = {
            "check_id": self.check_id,
            "claim_id": self.claim_id,
            "status": self.status.value,
            "evidence_id": self.evidence_id,
        }
        if self.failure_reason is not None:
            value["failure_reason"] = self.failure_reason
        return value


@dataclass(frozen=True)
class ContentAssuranceReport:
    """A publication decision containing identifiers and check outcomes only."""

    artifact_id: str
    revision: str
    content_digest: str
    reuse_key: str
    decision: ContentDecision
    claim_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    checks: tuple[ContentCheck, ...]
    abstention_reasons: tuple[str, ...] = ()
    refusal_code: str | None = None

    @property
    def passed(self) -> bool:
        """Return true only when the artifact is approved for publication."""

        return self.decision is ContentDecision.APPROVED

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only report safe for CI output."""

        return {
            "content_assurance_version": CONTENT_ASSURANCE_VERSION,
            "artifact_id": self.artifact_id,
            "revision": self.revision,
            "content_digest": self.content_digest,
            "reuse_key": self.reuse_key,
            "decision": self.decision.value,
            "passed": self.passed,
            "claim_ids": list(self.claim_ids),
            "source_ids": list(self.source_ids),
            "checks": [check.to_dict() for check in self.checks],
            "abstention_reasons": list(self.abstention_reasons),
            "refusal_code": self.refusal_code,
            "diagnostics": {
                "warnings": [
                    "This report evaluates synthetic metadata and source contracts; "
                    "it does not read or publish lesson text."
                ],
                "what_it_does_not_show": (
                    "It does not prove that a source is substantively correct, "
                    "that a lesson teaches effectively, or that a live deployment "
                    "would remain current after this check."
                ),
            },
        }


@dataclass(frozen=True)
class ContentAssuranceCase:
    """One deterministic reference-agent case and its expected control result."""

    case_id: str
    request: ContentAssuranceRequest
    artifact: ContentArtifact
    sources: tuple[ContentSource, ...]
    expected_decision: ContentDecision
    expected_reason: str | None = None


@dataclass(frozen=True)
class ContentAssuranceSuiteReport:
    """The positive path and deliberately degraded content controls."""

    reports: tuple[tuple[str, ContentAssuranceReport], ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return true only when the positive and every negative control behave."""

        return not self.controls_missed

    def to_dict(self) -> dict[str, object]:
        """Return metadata-only suite output."""

        return {
            "content_assurance_version": CONTENT_ASSURANCE_VERSION,
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
                    "The suite uses one approval path and explicit degraded "
                    "controls for stale, wrong-source, and drifted evidence."
                ],
                "what_it_does_not_show": (
                    "It does not establish live-model quality, source truth, "
                    "or production monitoring."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing summary without content payloads."""

        lines = [
            "# Technical Content Assurance Report",
            "",
            f"Decision: {'PASS' if self.passed else 'BLOCKED'}",
            "",
            "| Case | Decision | Reasons |",
            "| --- | --- | --- |",
        ]
        for case_id, report in self.reports:
            reasons = ", ".join(report.abstention_reasons) or "none"
            lines.append(
                f"| `{case_id}` | `{report.decision.value}` | `{reasons}` |"
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
                "This report contains identifiers, statuses, and hashes only; it does "
                "not contain lesson text or source payloads.",
            ]
        )
        return "\n".join(lines)


class TechnicalContentAssuranceAgent:
    """Review synthetic technical content against an explicit evidence contract."""

    agent_id = "technical-content-assurance"

    def review(
        self,
        request: ContentAssuranceRequest,
        artifact: ContentArtifact,
        sources: Iterable[ContentSource],
    ) -> ContentAssuranceReport:
        """Return approval, abstention, or refusal for one content artifact."""

        source_tuple = tuple(sources)
        invalid = _validate_request(request, artifact, source_tuple)
        if invalid is not None:
            return _refused_report(artifact, invalid)

        source_by_id = {source.source_id: source for source in source_tuple}
        checks: list[ContentCheck] = []
        reasons: list[str] = []
        source_ids: list[str] = []
        approved_sources = set(request.approved_source_ids)

        for claim in artifact.claims:
            source = source_by_id.get(claim.source_id)
            source_ids.append(claim.source_id)
            evidence_id = claim.source_id
            if source is None:
                checks.append(
                    ContentCheck(
                        check_id="source-available",
                        claim_id=claim.claim_id,
                        status=FindingStatus.FAILED,
                        evidence_id=evidence_id,
                        failure_reason="evidence_missing",
                    )
                )
                _append_unique(reasons, "evidence_missing")
                continue

            if (
                source.source_id not in approved_sources
                or not _official_documentation_url(source.source_url)
            ):
                checks.append(
                    ContentCheck(
                        check_id="source-authority",
                        claim_id=claim.claim_id,
                        status=FindingStatus.FAILED,
                        evidence_id=evidence_id,
                        failure_reason="evidence_wrong_source",
                    )
                )
                _append_unique(reasons, "evidence_wrong_source")
            else:
                checks.append(
                    ContentCheck(
                        check_id="source-authority",
                        claim_id=claim.claim_id,
                        status=FindingStatus.COMPLETED,
                        evidence_id=evidence_id,
                    )
                )

            if source.age_seconds is None or (
                source.age_seconds > request.max_age_seconds
            ):
                checks.append(
                    ContentCheck(
                        check_id="source-freshness",
                        claim_id=claim.claim_id,
                        status=FindingStatus.FAILED,
                        evidence_id=evidence_id,
                        failure_reason=(
                            "evidence_verification_unknown"
                            if source.age_seconds is None
                            else "evidence_stale"
                        ),
                    )
                )
                _append_unique(
                    reasons,
                    (
                        "evidence_verification_unknown"
                        if source.age_seconds is None
                        else "evidence_stale"
                    ),
                )
            else:
                checks.append(
                    ContentCheck(
                        check_id="source-freshness",
                        claim_id=claim.claim_id,
                        status=FindingStatus.COMPLETED,
                        evidence_id=evidence_id,
                    )
                )

            if source.source_digest != claim.expected_source_digest:
                checks.append(
                    ContentCheck(
                        check_id="source-integrity",
                        claim_id=claim.claim_id,
                        status=FindingStatus.FAILED,
                        evidence_id=evidence_id,
                        failure_reason="source_drift",
                    )
                )
                _append_unique(reasons, "source_drift")
            else:
                checks.append(
                    ContentCheck(
                        check_id="source-integrity",
                        claim_id=claim.claim_id,
                        status=FindingStatus.COMPLETED,
                        evidence_id=evidence_id,
                    )
                )

        decision = (
            ContentDecision.ABSTAIN
            if reasons
            else ContentDecision.APPROVED
        )
        return ContentAssuranceReport(
            artifact_id=artifact.artifact_id,
            revision=artifact.revision,
            content_digest=artifact.content_digest,
            reuse_key=artifact.reuse_key,
            decision=decision,
            claim_ids=tuple(claim.claim_id for claim in artifact.claims),
            source_ids=tuple(source_ids),
            checks=tuple(checks),
            abstention_reasons=tuple(reasons),
        )


class ContentAssuranceAdapter:
    """Expose the reference content agent through the harness adapter protocol."""

    agent_id = "content-assurance-reference"

    def run(self, request: ScenarioRequest, environment: object) -> AdapterRun:
        """Run one synthetic content case and emit identifier-only evidence."""

        del environment
        cases = {
            case.case_id: case for case in reference_content_assurance_cases()
        }
        case = cases.get(request.scenario_id)
        if case is None:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="unknown_content_case",
                    message="The content-assurance case is not registered.",
                    guidance="Use one of the checked-in synthetic content case identifiers.",
                )
            )
        if request.contract.scenario_id != request.scenario_id:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="content_contract_mismatch",
                    message="The content request contract does not match its case.",
                    guidance="Use the declarative content-assurance pack for this case.",
                )
            )

        source = case.sources[0] if case.sources else None
        recorder = TraceRecorder(
            scenario_id=request.scenario_id,
            agent_id=self.agent_id,
        )
        recorder.record_tool_call("read_content")
        recorder.record_tool_result(
            "read_content",
            "ok" if source is not None else "not_found",
            result_id=f"content-evidence-{case.case_id}",
            source=source.source_id if source is not None else None,
            age_seconds=source.age_seconds if source is not None else None,
        )
        report = TechnicalContentAssuranceAgent().review(
            case.request,
            case.artifact,
            case.sources,
        )
        if report.decision is ContentDecision.APPROVED:
            recorder.record_claim("claim:content_assured")
            recorder.record_answer("answer:publishable")
        else:
            recorder.record_claim("claim:content_requires_review")
            recorder.record_abstention(
                report.abstention_reasons[0]
                if report.abstention_reasons
                else "evidence_missing"
            )
        return recorder.finish()


def reference_content_assurance_cases() -> tuple[ContentAssuranceCase, ...]:
    """Return the public synthetic positive and negative-control cases."""

    expected_source_digest = _digest("approved-source-v1")
    artifact = ContentArtifact(
        artifact_id="lesson-mcp-boundary",
        revision="lesson-revision-003",
        content_digest=_digest("lesson-mcp-boundary-revision-003"),
        reuse_key="mcp-root-confinement",
        claims=(
            ContentClaim(
                claim_id="claim-root-confinement",
                source_id="source-approved-docs",
                expected_source_digest=expected_source_digest,
            ),
        ),
    )
    fresh_source = ContentSource(
        source_id="source-approved-docs",
        authority="public-reference-docs",
        source_url="https://docs.aws.amazon.com/",
        source_digest=expected_source_digest,
        age_seconds=300,
    )
    stale_source = ContentSource(
        source_id="source-approved-docs",
        authority="public-reference-docs",
        source_url="https://docs.aws.amazon.com/",
        source_digest=expected_source_digest,
        age_seconds=7200,
    )
    wrong_source_artifact = ContentArtifact(
        artifact_id=artifact.artifact_id,
        revision=artifact.revision,
        content_digest=artifact.content_digest,
        reuse_key=artifact.reuse_key,
        claims=(
            ContentClaim(
                claim_id="claim-root-confinement",
                source_id="source-unapproved-copy",
                expected_source_digest=expected_source_digest,
            ),
        ),
    )
    wrong_source = ContentSource(
        source_id="source-unapproved-copy",
        authority="unreviewed-copy",
        source_url="https://developers.openai.com/",
        source_digest=expected_source_digest,
        age_seconds=300,
    )
    drifted_source = ContentSource(
        source_id="source-approved-docs",
        authority="public-reference-docs",
        source_url="https://docs.aws.amazon.com/",
        source_digest="sha256:" + "0" * 64,
        age_seconds=300,
    )
    request = ContentAssuranceRequest(
        artifact_id=artifact.artifact_id,
        approved_source_ids=("source-approved-docs",),
        max_age_seconds=3600,
    )
    return (
        ContentAssuranceCase(
            case_id="fresh-approved",
            request=request,
            artifact=artifact,
            sources=(fresh_source,),
            expected_decision=ContentDecision.APPROVED,
        ),
        ContentAssuranceCase(
            case_id="stale-approved",
            request=request,
            artifact=artifact,
            sources=(stale_source,),
            expected_decision=ContentDecision.ABSTAIN,
            expected_reason="evidence_stale",
        ),
        ContentAssuranceCase(
            case_id="fresh-wrong-source",
            request=request,
            artifact=wrong_source_artifact,
            sources=(wrong_source,),
            expected_decision=ContentDecision.ABSTAIN,
            expected_reason="evidence_wrong_source",
        ),
        ContentAssuranceCase(
            case_id="source-drift",
            request=request,
            artifact=artifact,
            sources=(drifted_source,),
            expected_decision=ContentDecision.ABSTAIN,
            expected_reason="source_drift",
        ),
    )


def run_reference_content_assurance_suite() -> ContentAssuranceSuiteReport:
    """Run the positive path and verify that degraded cases are caught."""

    agent = TechnicalContentAssuranceAgent()
    reports: list[tuple[str, ContentAssuranceReport]] = []
    caught: list[str] = []
    missed: list[str] = []
    for case in reference_content_assurance_cases():
        report = agent.review(case.request, case.artifact, case.sources)
        reports.append((case.case_id, report))
        expected = case.expected_decision is report.decision
        reason_found = (
            case.expected_reason is None
            or case.expected_reason in report.abstention_reasons
        )
        if expected and reason_found:
            caught.append(case.case_id)
        else:
            missed.append(case.case_id)
    return ContentAssuranceSuiteReport(
        reports=tuple(reports),
        controls_caught=tuple(caught),
        controls_missed=tuple(missed),
    )


def _validate_request(
    request: ContentAssuranceRequest,
    artifact: ContentArtifact,
    sources: tuple[ContentSource, ...],
) -> str | None:
    if request.artifact_id != artifact.artifact_id:
        return "artifact_id_mismatch"
    if not _valid_identifier(request.artifact_id):
        return "invalid_artifact_id"
    if not _valid_identifier(artifact.revision):
        return "invalid_revision"
    if not _valid_digest(artifact.content_digest):
        return "invalid_content_digest"
    if not _valid_identifier(artifact.reuse_key):
        return "invalid_reuse_key"
    if not artifact.claims:
        return "missing_claims"
    claim_ids = [claim.claim_id for claim in artifact.claims]
    if len(claim_ids) != len(set(claim_ids)):
        return "duplicate_claim_id"
    for claim in artifact.claims:
        if not _valid_identifier(claim.claim_id):
            return "invalid_claim_id"
        if not _valid_identifier(claim.source_id):
            return "invalid_source_id"
        if not _valid_digest(claim.expected_source_digest):
            return "invalid_expected_source_digest"
    if (
        isinstance(request.max_age_seconds, bool)
        or not isinstance(request.max_age_seconds, (int, float))
        or request.max_age_seconds < 0
    ):
        return "invalid_max_age_seconds"
    if not request.approved_source_ids or len(
        request.approved_source_ids
    ) != len(set(request.approved_source_ids)):
        return "invalid_approved_source_ids"
    if any(not _valid_identifier(source_id) for source_id in request.approved_source_ids):
        return "invalid_approved_source_ids"
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        return "duplicate_source_id"
    for source in sources:
        if not _valid_identifier(source.source_id) or not _valid_identifier(
            source.authority
        ):
            return "invalid_source_metadata"
        if not _valid_digest(source.source_digest):
            return "invalid_source_digest"
        if not _official_documentation_url(source.source_url):
            return "unapproved_source_host"
        if source.age_seconds is not None and (
            isinstance(source.age_seconds, bool)
            or not isinstance(source.age_seconds, (int, float))
            or source.age_seconds < 0
        ):
            return "invalid_source_age"
    return None


def _refused_report(artifact: ContentArtifact, refusal_code: str) -> ContentAssuranceReport:
    return ContentAssuranceReport(
        artifact_id=artifact.artifact_id,
        revision=artifact.revision,
        content_digest=artifact.content_digest,
        reuse_key=artifact.reuse_key,
        decision=ContentDecision.REFUSED,
        claim_ids=tuple(claim.claim_id for claim in artifact.claims),
        source_ids=tuple(claim.source_id for claim in artifact.claims),
        checks=(),
        refusal_code=refusal_code,
    )


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _official_documentation_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in _OFFICIAL_DOCUMENTATION_HOSTS
        and not parsed.username
        and not parsed.password
    )


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
