"""Bounded in-memory source ingestion for technical-content assurance.

The pipeline accepts source bytes only for the duration of one local call. It
normalizes and fingerprints those bytes in memory, binds a reviewed claim index
to source-section identifiers, and then routes the resulting metadata through
the existing claim-assurance agent.

The report never contains source bytes, normalized text, claim text, or parsed
HTML. A support status is evidence supplied by the claim index; it is not a
claim that this module independently proved semantic truth.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from html.parser import HTMLParser
from urllib.parse import urlparse

from .content_assurance import (
    ClaimSupport,
    ContentArtifact,
    ContentAssuranceReport,
    ContentAssuranceRequest,
    ContentClaim,
    ContentDecision,
    ContentSource,
    TechnicalContentAssuranceAgent,
)
from .public_sources import OFFICIAL_DOCUMENTATION_HOSTS


CONTENT_PIPELINE_VERSION = 1
DEFAULT_MAX_SOURCE_BYTES = 2_000_000
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SUPPORT_STATES = frozenset(
    {"supported", "unsupported", "conflicting", "ambiguous"}
)


class PipelineDecision(str, Enum):
    """The safe outcome of one source-ingestion pipeline run."""

    APPROVED = "approved"
    ABSTAIN = "abstain"
    REFUSED = "refused"


@dataclass(frozen=True)
class PipelineClaim:
    """A reviewed claim-to-section mapping without claim text."""

    claim_id: str
    section_id: str
    support_status: str


@dataclass(frozen=True)
class ContentPipelineRequest:
    """Input to one bounded in-memory source-ingestion run."""

    case_id: str
    artifact_id: str
    artifact_revision: str
    artifact_digest: str
    reuse_key: str
    source_id: str
    authority: str
    source_url: str
    source_bytes: bytes
    age_seconds: float | None
    claims: tuple[PipelineClaim, ...]
    approved_source_ids: tuple[str, ...]
    max_age_seconds: float
    expected_source_digest: str | None = None
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES


@dataclass(frozen=True)
class ContentPipelineReport:
    """Metadata-only output from one source-ingestion and assurance run."""

    case_id: str
    decision: PipelineDecision
    source_id: str
    source_digest: str | None
    normalized_digest: str | None
    byte_count: int
    normalized_byte_count: int | None
    section_ids: tuple[str, ...]
    claim_evidence_ids: tuple[str, ...]
    abstention_reasons: tuple[str, ...] = ()
    refusal_code: str | None = None

    @property
    def passed(self) -> bool:
        """Return true only when the source and every claim are approved."""

        return self.decision is PipelineDecision.APPROVED

    def to_dict(self) -> dict[str, object]:
        """Return output safe for logs, CI summaries, and artifacts."""

        return {
            "content_pipeline_version": CONTENT_PIPELINE_VERSION,
            "case_id": self.case_id,
            "decision": self.decision.value,
            "passed": self.passed,
            "source_id": self.source_id,
            "source_digest": self.source_digest,
            "normalized_digest": self.normalized_digest,
            "byte_count": self.byte_count,
            "normalized_byte_count": self.normalized_byte_count,
            "section_ids": list(self.section_ids),
            "claim_evidence_ids": list(self.claim_evidence_ids),
            "abstention_reasons": list(self.abstention_reasons),
            "refusal_code": self.refusal_code,
            "diagnostics": {
                "warnings": [
                    "Source bytes and normalized text were processed in memory "
                    "and discarded; this report contains metadata only."
                ],
                "what_it_does_not_show": (
                    "It does not prove semantic claim truth, source completeness, "
                    "or that a later retrieval will return the same bytes."
                ),
            },
        }


@dataclass(frozen=True)
class ContentPipelineCase:
    """A deterministic pipeline case and its expected decision."""

    case_id: str
    request: ContentPipelineRequest
    expected_decision: PipelineDecision
    expected_reason: str | None = None


@dataclass(frozen=True)
class ContentPipelineSuiteReport:
    """The pipeline positive path and deliberate ingestion controls."""

    reports: tuple[tuple[str, ContentPipelineReport], ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return true only when every declared control behaves as expected."""

        return not self.controls_missed

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only suite report."""

        return {
            "content_pipeline_version": CONTENT_PIPELINE_VERSION,
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
                    "The suite validates in-memory source ingestion and routes "
                    "claim metadata through the content-assurance contract."
                ],
                "what_it_does_not_show": (
                    "It does not establish semantic truth or retain source text "
                    "for later inspection."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing summary without source content."""

        lines = [
            "# Content Assurance Pipeline Report",
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
                "This report contains identifiers, sizes, and hashes only.",
            ]
        )
        return "\n".join(lines)


class _TextNormalizer(HTMLParser):
    """Collect text only long enough to calculate a normalized fingerprint."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def normalized_text(self) -> str:
        return " ".join(" ".join(self._parts).split())


def run_content_assurance_pipeline(
    request: ContentPipelineRequest,
) -> ContentPipelineReport:
    """Ingest, fingerprint, and evaluate one source without retaining its body."""

    refusal = _validate_request(request)
    if refusal is not None:
        return _refused_pipeline_report(request, refusal)

    source_digest = _sha256(request.source_bytes)
    try:
        decoded = request.source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _refused_pipeline_report(request, "source_not_utf8")

    normalizer = _TextNormalizer()
    normalizer.feed(decoded)
    normalizer.close()
    normalized = normalizer.normalized_text()
    normalized_digest = _sha256(normalized.encode("utf-8"))

    expected_digest = request.expected_source_digest or source_digest
    source = ContentSource(
        source_id=request.source_id,
        authority=request.authority,
        source_url=request.source_url,
        source_digest=source_digest,
        age_seconds=request.age_seconds,
        claim_support=tuple(
            ClaimSupport(claim.claim_id, claim.support_status)
            for claim in request.claims
        ),
    )
    artifact = ContentArtifact(
        artifact_id=request.artifact_id,
        revision=request.artifact_revision,
        content_digest=request.artifact_digest,
        reuse_key=request.reuse_key,
        claims=tuple(
            ContentClaim(
                claim_id=claim.claim_id,
                source_id=request.source_id,
                expected_source_digest=expected_digest,
            )
            for claim in request.claims
        ),
    )
    assurance = TechnicalContentAssuranceAgent().review(
        ContentAssuranceRequest(
            artifact_id=request.artifact_id,
            approved_source_ids=request.approved_source_ids,
            max_age_seconds=request.max_age_seconds,
        ),
        artifact,
        (source,),
    )
    return _pipeline_report_from_assurance(
        request,
        assurance,
        source_digest=source_digest,
        normalized_digest=normalized_digest,
        normalized_byte_count=len(normalized.encode("utf-8")),
    )


def reference_content_pipeline_cases() -> tuple[ContentPipelineCase, ...]:
    """Return deterministic ingestion, source, and claim controls."""

    body = (
        b"<html><body><h1>Synthetic lesson</h1>"
        b"<p>Approved technical guidance fixture.</p></body></html>"
    )
    source_digest = _sha256(body)
    base = {
        "artifact_id": "lesson-pipeline",
        "artifact_revision": "lesson-pipeline-revision-001",
        "artifact_digest": _sha256(b"synthetic-lesson-revision-001"),
        "reuse_key": "pipeline-reference",
        "source_id": "source-approved-docs",
        "authority": "public-reference-docs",
        "source_url": "https://docs.aws.amazon.com/",
        "source_bytes": body,
        "age_seconds": 300,
        "claims": (
            PipelineClaim(
                claim_id="claim-pipeline-supported",
                section_id="section-synthetic-guidance",
                support_status="supported",
            ),
        ),
        "approved_source_ids": ("source-approved-docs",),
        "max_age_seconds": 3600,
    }
    return (
        ContentPipelineCase(
            case_id="pipeline-approved",
            request=ContentPipelineRequest(
                case_id="pipeline-approved",
                **base,
            ),
            expected_decision=PipelineDecision.APPROVED,
        ),
        ContentPipelineCase(
            case_id="pipeline-unsupported-claim",
            request=ContentPipelineRequest(
                case_id="pipeline-unsupported-claim",
                **{
                    **base,
                    "claims": (
                        PipelineClaim(
                            claim_id="claim-pipeline-unsupported",
                            section_id="section-synthetic-guidance",
                            support_status="unsupported",
                        ),
                    ),
                },
            ),
            expected_decision=PipelineDecision.ABSTAIN,
            expected_reason="claim_unsupported",
        ),
        ContentPipelineCase(
            case_id="pipeline-stale-source",
            request=ContentPipelineRequest(
                case_id="pipeline-stale-source",
                **{**base, "age_seconds": 7200},
            ),
            expected_decision=PipelineDecision.ABSTAIN,
            expected_reason="evidence_stale",
        ),
        ContentPipelineCase(
            case_id="pipeline-source-drift",
            request=ContentPipelineRequest(
                case_id="pipeline-source-drift",
                **{
                    **base,
                    "expected_source_digest": "sha256:" + "0" * 64,
                },
            ),
            expected_decision=PipelineDecision.ABSTAIN,
            expected_reason="source_drift",
        ),
        ContentPipelineCase(
            case_id="pipeline-unapproved-host",
            request=ContentPipelineRequest(
                case_id="pipeline-unapproved-host",
                **{
                    **base,
                    "source_url": "https://example.invalid/",
                },
            ),
            expected_decision=PipelineDecision.REFUSED,
            expected_reason="unapproved_source_host",
        ),
    )


def run_reference_content_pipeline_suite() -> ContentPipelineSuiteReport:
    """Run the bounded pipeline controls and verify their expected outcomes."""

    reports: list[tuple[str, ContentPipelineReport]] = []
    caught: list[str] = []
    missed: list[str] = []
    for case in reference_content_pipeline_cases():
        report = run_content_assurance_pipeline(case.request)
        reports.append((case.case_id, report))
        expected = case.expected_decision is report.decision
        reason_found = (
            case.expected_reason is None
            or case.expected_reason in report.abstention_reasons
            or case.expected_reason == report.refusal_code
        )
        if expected and reason_found:
            caught.append(case.case_id)
        else:
            missed.append(case.case_id)
    return ContentPipelineSuiteReport(
        reports=tuple(reports),
        controls_caught=tuple(caught),
        controls_missed=tuple(missed),
    )


def _validate_request(request: ContentPipelineRequest) -> str | None:
    if not _valid_identifier(request.case_id):
        return "invalid_case_id"
    for value, code in (
        (request.artifact_id, "invalid_artifact_id"),
        (request.artifact_revision, "invalid_artifact_revision"),
        (request.reuse_key, "invalid_reuse_key"),
        (request.source_id, "invalid_source_id"),
        (request.authority, "invalid_authority"),
    ):
        if not _valid_identifier(value):
            return code
    if not _valid_digest(request.artifact_digest):
        return "invalid_artifact_digest"
    if not isinstance(request.source_bytes, bytes) or not request.source_bytes:
        return "missing_source_bytes"
    if request.max_source_bytes < 1:
        return "invalid_source_limit"
    if len(request.source_bytes) > request.max_source_bytes:
        return "source_too_large"
    if not _official_url(request.source_url):
        return "unapproved_source_host"
    if request.age_seconds is not None and (
        isinstance(request.age_seconds, bool)
        or not isinstance(request.age_seconds, (int, float))
        or request.age_seconds < 0
    ):
        return "invalid_source_age"
    if request.expected_source_digest is not None and not _valid_digest(
        request.expected_source_digest
    ):
        return "invalid_expected_source_digest"
    if not request.claims:
        return "missing_claims"
    claim_ids = [claim.claim_id for claim in request.claims]
    if len(claim_ids) != len(set(claim_ids)):
        return "duplicate_claim_id"
    section_ids = [claim.section_id for claim in request.claims]
    if len(section_ids) != len(set(section_ids)):
        return "duplicate_section_id"
    for claim in request.claims:
        if not _valid_identifier(claim.claim_id):
            return "invalid_claim_id"
        if not _valid_identifier(claim.section_id):
            return "invalid_section_id"
        if claim.support_status not in _SUPPORT_STATES:
            return "invalid_claim_support_status"
    if not request.approved_source_ids or len(
        request.approved_source_ids
    ) != len(set(request.approved_source_ids)):
        return "invalid_approved_source_ids"
    if any(not _valid_identifier(value) for value in request.approved_source_ids):
        return "invalid_approved_source_ids"
    if (
        isinstance(request.max_age_seconds, bool)
        or not isinstance(request.max_age_seconds, (int, float))
        or request.max_age_seconds < 0
    ):
        return "invalid_max_age_seconds"
    return None


def _pipeline_report_from_assurance(
    request: ContentPipelineRequest,
    assurance: ContentAssuranceReport,
    *,
    source_digest: str,
    normalized_digest: str,
    normalized_byte_count: int,
) -> ContentPipelineReport:
    evidence_ids = tuple(
        f"evidence:{request.source_id}:{claim.claim_id}:{claim.section_id}"
        for claim in request.claims
    )
    return ContentPipelineReport(
        case_id=request.case_id,
        decision=PipelineDecision(assurance.decision.value),
        source_id=request.source_id,
        source_digest=source_digest,
        normalized_digest=normalized_digest,
        byte_count=len(request.source_bytes),
        normalized_byte_count=normalized_byte_count,
        section_ids=tuple(claim.section_id for claim in request.claims),
        claim_evidence_ids=evidence_ids,
        abstention_reasons=assurance.abstention_reasons,
        refusal_code=assurance.refusal_code,
    )


def _refused_pipeline_report(
    request: ContentPipelineRequest,
    refusal_code: str,
) -> ContentPipelineReport:
    return ContentPipelineReport(
        case_id=request.case_id,
        decision=PipelineDecision.REFUSED,
        source_id=request.source_id,
        source_digest=None,
        normalized_digest=None,
        byte_count=len(request.source_bytes)
        if isinstance(request.source_bytes, bytes)
        else 0,
        normalized_byte_count=None,
        section_ids=tuple(
            claim.section_id
            for claim in request.claims
            if isinstance(claim.section_id, str)
        ),
        claim_evidence_ids=(),
        refusal_code=refusal_code,
    )


def _official_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in OFFICIAL_DOCUMENTATION_HOSTS
        and not parsed.username
        and not parsed.password
    )


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
