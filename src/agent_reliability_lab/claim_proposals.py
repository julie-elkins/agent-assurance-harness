"""Untrusted claim-proposal boundary for technical-content assurance.

The proposal worker suggests claim and section identifiers. It does not decide
whether a claim is true, current, safe to publish, or approved by a reviewer.
The worker receives source bytes in memory, but its result contains identifiers
and a source fingerprint only.

Design rules:

1. Proposal output is validated before the evidence pipeline sees it.
2. Empty, duplicate, fabricated, incomplete, stale, or raw-content-bearing
   proposals are structured refusals.
3. The synthetic worker is deterministic and deliberately does not claim
   semantic extraction quality.
4. The public report never contains source bytes, claim text, quotes, or
   provider output.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .content_pipeline import PipelineClaim


CLAIM_PROPOSAL_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_RAW_FIELDS = frozenset({"claim_text", "quote", "content", "source_text"})


class ProposalStatus(str, Enum):
    """The proposal-stage outcome before evidence evaluation."""

    COMPLETED = "completed"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass(frozen=True)
class ClaimProposalRequest:
    """Typed input sent from the Course Doctor to a proposal worker."""

    course_id: str
    course_revision: str
    source_id: str
    source_bytes: bytes
    known_claims: tuple[PipelineClaim, ...]
    required_claim_ids: tuple[str, ...]

    @property
    def source_digest(self) -> str:
        """Return the one-way source fingerprint used for binding."""

        return f"sha256:{hashlib.sha256(self.source_bytes).hexdigest()}"


@dataclass(frozen=True)
class ClaimProposal:
    """One proposal without claim text or a source quote."""

    proposal_id: str
    claim_id: str
    section_id: str
    source_digest: str

    def to_dict(self) -> dict[str, str]:
        """Return safe proposal metadata."""

        return {
            "proposal_id": self.proposal_id,
            "claim_id": self.claim_id,
            "section_id": self.section_id,
            "source_digest": self.source_digest,
        }


@dataclass(frozen=True)
class ClaimProposalResult:
    """The proposal worker's metadata-only result."""

    status: ProposalStatus
    proposals: tuple[ClaimProposal, ...] = ()
    refusal_code: str | None = None
    failure_code: str | None = None

    @property
    def usable(self) -> bool:
        """Return whether this result passed the proposal boundary."""

        return self.status is ProposalStatus.COMPLETED and not self.refusal_code

    def to_dict(self) -> dict[str, object]:
        """Return a report-safe proposal result."""

        return {
            "claim_proposal_version": CLAIM_PROPOSAL_VERSION,
            "status": self.status.value,
            "usable": self.usable,
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "proposal_count": len(self.proposals),
            "refusal_code": self.refusal_code,
            "failure_code": self.failure_code,
            "diagnostics": {
                "warnings": [
                    "Proposals are unverified identifiers and cannot authorize "
                    "publication."
                ],
                "what_it_does_not_show": (
                    "It does not prove semantic claim truth, source completeness, "
                    "or human approval."
                ),
            },
        }


class ClaimProposalWorker(Protocol):
    """Protocol for a replaceable proposal-producing agent."""

    def propose(self, request: ClaimProposalRequest) -> ClaimProposalResult:
        """Return candidate identifiers without making an approval decision."""


class SyntheticClaimProposalWorker:
    """Deterministic stand-in for a future model-backed proposal worker."""

    def propose(self, request: ClaimProposalRequest) -> ClaimProposalResult:
        """Mirror the reviewed synthetic claim registry as candidate proposals."""

        # MODELLING ASSUMPTION: the public worker mirrors synthetic metadata instead
        # of inferring semantics. A live extractor would need its own model, spend,
        # privacy, and semantic-quality review, so pretending this fixture is an
        # extraction score would overstate what CI proves.
        return ClaimProposalResult(
            status=ProposalStatus.COMPLETED,
            proposals=tuple(
                ClaimProposal(
                    proposal_id=f"proposal:{request.course_id}:{claim.claim_id}",
                    claim_id=claim.claim_id,
                    section_id=claim.section_id,
                    source_digest=request.source_digest,
                )
                for claim in request.known_claims
            ),
        )


def parse_claim_proposal_output(payload: object) -> ClaimProposalResult:
    """Parse an external worker payload without allowing raw content through."""

    if not isinstance(payload, dict):
        return _refused("proposal_output_not_object")
    if _contains_raw_field(payload):
        return _refused("raw_content_field")
    proposals_value = payload.get("proposals")
    if not isinstance(proposals_value, list):
        return _refused("proposals_missing_or_not_list")
    proposals: list[ClaimProposal] = []
    for proposal in proposals_value:
        if not isinstance(proposal, dict):
            return _refused("proposal_not_object")
        if set(proposal) - {
            "proposal_id",
            "claim_id",
            "section_id",
            "source_digest",
        }:
            return _refused("unknown_proposal_field")
        try:
            values = {
                key: proposal[key]
                for key in (
                    "proposal_id",
                    "claim_id",
                    "section_id",
                    "source_digest",
                )
            }
        except KeyError:
            return _refused("proposal_field_missing")
        if not all(isinstance(value, str) and value for value in values.values()):
            return _refused("proposal_field_invalid")
        proposals.append(ClaimProposal(**values))
    return ClaimProposalResult(
        status=ProposalStatus.COMPLETED,
        proposals=tuple(proposals),
    )


def validate_claim_proposal_result(
    request: ClaimProposalRequest,
    result: ClaimProposalResult,
) -> ClaimProposalResult:
    """Validate proposal identity and coverage before evidence evaluation."""

    if result.status is not ProposalStatus.COMPLETED:
        return result
    if not result.proposals:
        return _refused("empty_proposal_set")
    proposal_ids = [proposal.proposal_id for proposal in result.proposals]
    claim_ids = [proposal.claim_id for proposal in result.proposals]
    if len(proposal_ids) != len(set(proposal_ids)):
        return _refused("duplicate_proposal_id")
    if len(claim_ids) != len(set(claim_ids)):
        return _refused("duplicate_claim_id")
    known = {claim.claim_id: claim for claim in request.known_claims}
    required = set(request.required_claim_ids)
    proposed = set(claim_ids)
    if proposed - set(known):
        return _refused("fabricated_claim_id")
    if required - proposed:
        return _refused("missing_required_claim")
    if any(
        proposal.section_id != known[proposal.claim_id].section_id
        for proposal in result.proposals
    ):
        return _refused("claim_section_mismatch")
    if any(
        proposal.source_digest != request.source_digest
        for proposal in result.proposals
    ):
        return _refused("proposal_source_drift")
    if any(
        not _safe_identifier(value)
        for proposal in result.proposals
        for value in (
            proposal.proposal_id,
            proposal.claim_id,
            proposal.section_id,
        )
    ):
        return _refused("proposal_identifier_invalid")
    return result


def proposed_pipeline_claims(
    request: ClaimProposalRequest,
    result: ClaimProposalResult,
) -> tuple[PipelineClaim, ...]:
    """Translate validated proposals to the existing evidence contract."""

    known = {claim.claim_id: claim for claim in request.known_claims}
    return tuple(
        known[proposal.claim_id]
        for proposal in result.proposals
        if proposal.claim_id in known
    )


def _contains_raw_field(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in _RAW_FIELDS or _contains_raw_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_raw_field(item) for item in value)
    return False


def _safe_identifier(value: str) -> bool:
    return bool(_IDENTIFIER.fullmatch(value))


def _refused(code: str) -> ClaimProposalResult:
    return ClaimProposalResult(
        status=ProposalStatus.REFUSED,
        refusal_code=code,
    )
