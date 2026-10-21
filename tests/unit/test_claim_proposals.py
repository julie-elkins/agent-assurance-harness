from agent_reliability_lab.claim_proposals import (
    ClaimProposal,
    ClaimProposalRequest,
    ClaimProposalResult,
    ProposalStatus,
    SyntheticClaimProposalWorker,
    parse_claim_proposal_output,
    validate_claim_proposal_result,
)
from agent_reliability_lab.content_pipeline import PipelineClaim
from agent_reliability_lab.course_doctor import (
    CourseDoctorCoordinator,
    ReviewDisposition,
    reference_course_doctor_cases,
)


def _proposal_request():
    case = reference_course_doctor_cases()[0]
    pipeline = case.request.freshness_request.pipeline_request
    return ClaimProposalRequest(
        course_id=case.course_id,
        course_revision=case.request.course_revision,
        source_id=pipeline.source_id,
        source_bytes=pipeline.source_bytes,
        known_claims=pipeline.claims,
        required_claim_ids=tuple(claim.claim_id for claim in pipeline.claims),
    )


def test_synthetic_worker_passes_only_identifier_metadata():
    request = _proposal_request()
    result = validate_claim_proposal_result(
        request,
        SyntheticClaimProposalWorker().propose(request),
    )

    assert result.usable
    assert len(result.proposals) == 1
    assert "Approved technical guidance fixture" not in str(result.to_dict())


def test_raw_content_is_refused_at_proposal_boundary():
    result = parse_claim_proposal_output(
        {
            "proposals": [
                {
                    "proposal_id": "proposal:one",
                    "claim_id": "claim:one",
                    "section_id": "section:one",
                    "source_digest": "sha256:" + "a" * 64,
                    "claim_text": "private claim text",
                }
            ]
        }
    )

    assert result.status is ProposalStatus.REFUSED
    assert result.refusal_code == "raw_content_field"
    assert "private claim text" not in str(result.to_dict())


def test_empty_duplicate_and_fabricated_proposals_are_refused():
    request = _proposal_request()
    valid = SyntheticClaimProposalWorker().propose(request).proposals[0]

    assert validate_claim_proposal_result(
        request,
        ClaimProposalResult(status=ProposalStatus.COMPLETED),
    ).refusal_code == "empty_proposal_set"

    assert validate_claim_proposal_result(
        request,
        ClaimProposalResult(
            status=ProposalStatus.COMPLETED,
            proposals=(valid, valid),
        ),
    ).refusal_code == "duplicate_proposal_id"

    fabricated = ClaimProposal(
        proposal_id="proposal:fabricated",
        claim_id="claim:fabricated",
        section_id=valid.section_id,
        source_digest=request.source_digest,
    )
    assert validate_claim_proposal_result(
        request,
        ClaimProposalResult(
            status=ProposalStatus.COMPLETED,
            proposals=(fabricated,),
        ),
    ).refusal_code == "fabricated_claim_id"


def test_incomplete_and_source_drifted_proposals_are_refused():
    request = _proposal_request()
    first = request.known_claims[0]
    second = PipelineClaim(
        claim_id="claim:second",
        section_id="section:second",
        support_status="supported",
    )
    expanded = ClaimProposalRequest(
        course_id=request.course_id,
        course_revision=request.course_revision,
        source_id=request.source_id,
        source_bytes=request.source_bytes,
        known_claims=(first, second),
        required_claim_ids=(first.claim_id, second.claim_id),
    )
    first_proposal = ClaimProposal(
        proposal_id="proposal:first",
        claim_id=first.claim_id,
        section_id=first.section_id,
        source_digest=expanded.source_digest,
    )
    assert validate_claim_proposal_result(
        expanded,
        ClaimProposalResult(
            status=ProposalStatus.COMPLETED,
            proposals=(first_proposal,),
        ),
    ).refusal_code == "missing_required_claim"

    drifted = ClaimProposal(
        proposal_id="proposal:drifted",
        claim_id=first.claim_id,
        section_id=first.section_id,
        source_digest="sha256:" + "b" * 64,
    )
    assert validate_claim_proposal_result(
        request,
        ClaimProposalResult(
            status=ProposalStatus.COMPLETED,
            proposals=(drifted,),
        ),
    ).refusal_code == "proposal_source_drift"


def test_fabricated_proposal_blocks_course_doctor_before_evidence_review(tmp_path):
    doctor_request = reference_course_doctor_cases()[0].request

    class FabricatedWorker:
        def propose(self, proposal_request):
            return ClaimProposalResult(
                status=ProposalStatus.COMPLETED,
                proposals=(
                    ClaimProposal(
                        proposal_id="proposal:fabricated",
                        claim_id="claim:fabricated",
                        section_id=proposal_request.known_claims[0].section_id,
                        source_digest=proposal_request.source_digest,
                    ),
                ),
            )

    report = CourseDoctorCoordinator(
        proposal_worker=FabricatedWorker(),
    ).review(
        (
            doctor_request,
        ),
        workspace=tmp_path,
    )

    packet = report.packets[0]
    assert not report.passed
    assert packet.recommended_disposition is ReviewDisposition.BLOCKED
    assert packet.proposal_status is ProposalStatus.REFUSED
    assert packet.failure_code == "proposal_fabricated_claim_id"
    assert packet.source_digest is None
