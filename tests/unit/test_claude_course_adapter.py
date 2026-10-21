import json

from agent_reliability_lab.claude_course_adapter import (
    ClaimVerificationState,
    VerifierRow,
    adapt_verifier_rows,
    run_claude_course_adapter,
)


def test_adapter_preserves_evidence_tiers_without_source_text():
    rows = (
        VerifierRow(
            row_id="lesson-a:claim-1",
            lesson_id="lesson-a",
            claim_index=1,
            tier="GUIDE",
            source_url=None,
            source_reference="EG § 2 read 2026-10-01",
            source_read_date="2026-10-01",
            quote="private guide text must not escape",
        ),
        VerifierRow(
            row_id="lesson-a:claim-2",
            lesson_id="lesson-a",
            claim_index=2,
            tier="VERBATIM",
            source_url="https://docs.example.test/guide",
            source_reference="official docs read 2026-10-01",
            source_read_date="2026-10-01",
            quote="private source quote must not escape",
        ),
        VerifierRow(
            row_id="lesson-b:claim-1",
            lesson_id="lesson-b",
            claim_index=1,
            tier="IDENTIFIER",
            source_url="https://docs.example.test/tools",
            source_reference="official docs read 2026-10-01",
            source_read_date="2026-10-01",
            identifiers=("--safe-flag",),
        ),
        VerifierRow(
            row_id="lesson-c:claim-1",
            lesson_id="lesson-c",
            claim_index=1,
            tier="UNCOVERED",
            source_url="https://docs.example.test/claims",
            source_reference="official docs read 2026-10-01",
            source_read_date=None,
        ),
    )
    report = adapt_verifier_rows(
        rows,
        course_id="synthetic-course",
        course_revision="abc123",
        outcomes={
            "lesson-a:claim-1": ClaimVerificationState.GUIDE_REFERENCE_ONLY,
            "lesson-a:claim-2": ClaimVerificationState.VERBATIM_NOT_FOUND,
            "lesson-b:claim-1": ClaimVerificationState.IDENTIFIER_PRESENT_ONLY,
            "lesson-c:claim-1": ClaimVerificationState.UNCOVERED,
        },
        pages_fetched=2,
    )

    payload = json.dumps(report.to_dict(), sort_keys=True)
    assert report.decision == "review_required"
    assert report.counts["rows_total"] == 4
    assert report.counts["counts_reconcile"] is True
    assert report.counts["verbatim_not_found"] == 1
    assert report.known_findings[0].locator.lesson_id == "lesson-a"
    assert "private guide text" not in payload
    assert "private source quote" not in payload
    assert "private guide text" not in report.to_markdown()
    assert "source_reference" not in payload


def test_adapter_refuses_missing_course_root_without_leaking_paths(tmp_path):
    report = run_claude_course_adapter(tmp_path / "does-not-exist")

    assert report.refusal_code == "course_root_missing"
    assert report.decision == "blocked"
    assert not report.passed
    assert str(tmp_path) not in json.dumps(report.to_dict(), sort_keys=True)
    assert "course_root_missing" in report.to_markdown()


def test_adapter_refuses_invalid_limits():
    row = VerifierRow(
        row_id="lesson:claim-1",
        lesson_id="lesson",
        claim_index=1,
        tier="GUIDE",
        source_url=None,
        source_reference="EG § 1",
        source_read_date=None,
    )
    report = adapt_verifier_rows(
        (row,),
        course_id="synthetic-course",
        course_revision=None,
        outcomes={},
        max_rows=0,
    )

    assert report.refusal_code == "invalid_limits"
    assert report.counts["rows_total"] == 0
