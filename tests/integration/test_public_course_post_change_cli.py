import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.claude_course_adapter import ClaimVerificationState
from agent_reliability_lab.public_course_change_plan import (
    PublicCourseChangePlan,
    PublicCourseChangePlanItem,
)
from agent_reliability_lab.public_course_review import (
    HumanDisposition,
    ReviewPriority,
)


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "public_course_post_change.py"


def test_post_change_cli_writes_safe_verification(tmp_path):
    plan = PublicCourseChangePlan(
        course_id="claude-course",
        course_revision="before-revision",
        packet_digest="sha256:packet",
        adjudication_decision="adjudicated",
        course_evidence_decision="review_required",
        items=(
            PublicCourseChangePlanItem(
                finding_id="claude-course:lesson-a:claim-1",
                lesson_id="lesson-a",
                claim_index=1,
                state=ClaimVerificationState.VERBATIM_NOT_FOUND,
                priority=ReviewPriority.REVIEW,
                disposition=HumanDisposition.RESOLVED,
                proposed_action="inspect_source_alignment",
                required_recheck="rerun_public_course_verifier_after_human_change",
            ),
        ),
    ).to_dict()
    report = {
        "claude_course_adapter_version": 1,
        "course_id": "claude-course",
        "course_revision": "after-revision",
        "decision": "review_required",
        "offline": False,
        "refusal_code": None,
        "counts": {"rows_total": 1, "counts_reconcile": True},
        "results": [
            {
                "row_id": "lesson-a:claim-1",
                "state": ClaimVerificationState.VERBATIM_VERIFIED.value,
                "reason_code": "verbatim_verified",
                "locator": {"lesson_id": "lesson-a", "claim_index": 1},
            }
        ],
    }
    plan_path = tmp_path / "change-plan.json"
    report_path = tmp_path / "post-report.json"
    output_path = tmp_path / "post-change.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--change-plan",
            str(plan_path),
            "--post-report",
            str(report_path),
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
    assert output["decision"] == "verified_targeted_scope"
    assert "human approval" in result.stdout
