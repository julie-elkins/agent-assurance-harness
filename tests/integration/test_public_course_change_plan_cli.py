import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.claude_course_adapter import ClaimVerificationState
from agent_reliability_lab.public_course_adjudication import (
    build_public_course_adjudication,
)
from agent_reliability_lab.public_course_review import (
    PublicCourseReviewFinding,
    PublicCourseReviewPacket,
    ReviewPriority,
)


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "public_course_change_plan.py"


def test_change_plan_cli_emits_metadata_only_output(tmp_path):
    packet = PublicCourseReviewPacket(
        course_id="claude-course",
        course_revision="abc123",
        adapter_decision="review_required",
        counts={"rows_total": 1, "verbatim_not_found": 1, "counts_reconcile": True},
        findings=(
            PublicCourseReviewFinding(
                finding_id="claude-course:lesson-a:claim-1",
                lesson_id="lesson-a",
                claim_index=1,
                evidence_tier="VERBATIM",
                state=ClaimVerificationState.VERBATIM_NOT_FOUND,
                reason_code="verbatim_not_found",
                source_url="https://docs.example.test/guide",
                source_read_date="2026-10-22",
                priority=ReviewPriority.REVIEW,
                recommended_action="inspect_source_alignment",
            ),
        ),
        total_known_findings=1,
        total_unverified_rows=1,
        max_findings=100,
        truncated=False,
    ).to_dict()
    adjudication = build_public_course_adjudication(
        packet,
        {
            "public_course_adjudication_version": 1,
            "packet_digest": packet["packet_digest"],
            "course_id": packet["course_id"],
            "course_revision": packet["course_revision"],
            "reviewer_id": "human-reviewer",
            "decisions": [
                {
                    "finding_id": packet["findings"][0]["finding_id"],
                    "disposition": "resolved",
                }
            ],
        },
    ).to_dict()
    packet_path = tmp_path / "packet.json"
    adjudication_path = tmp_path / "adjudication.json"
    output_path = tmp_path / "change-plan.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    adjudication_path.write_text(json.dumps(adjudication), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--packet",
            str(packet_path),
            "--adjudication",
            str(adjudication_path),
            "--output",
            str(output_path),
            "--markdown",
            "--fail-on-block",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert output["decision"] == "ready_for_human_approval"
    assert "inspect_source_alignment" in result.stdout
    assert "private course text" not in result.stdout
