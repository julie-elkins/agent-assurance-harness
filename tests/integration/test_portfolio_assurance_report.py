import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "portfolio_assurance_report.py"


def test_portfolio_report_passes_and_writes_json(tmp_path):
    output = tmp_path / "portfolio.json"
    workspace = tmp_path / "workspace"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--workspace",
            str(workspace),
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["portfolio_assurance_version"] == 3
    assert report["passed"] is True
    assert report["decision"] == "ready_for_human_review"
    assert report["controls_missed"] == []
    assert report["negative_control"]["caught"] is True
    assert len(report["lanes"]) == 6
    assert any(
        lane["lane_id"] == "agent_memory_policy"
        for lane in report["lanes"]
    )
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_portfolio_markdown_explains_the_human_boundary():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Portfolio Assurance Report" in result.stdout
    assert "`agent_assurance`" in result.stdout
    assert "`instructor_calibration`" in result.stdout
    assert "does not replace human review" in result.stdout


def test_portfolio_markdown_includes_safe_public_course_locator(monkeypatch, tmp_path):
    from agent_reliability_lab import portfolio_report
    from agent_reliability_lab.claude_course_adapter import (
        ClaimVerificationState,
        VerifierRow,
        adapt_verifier_rows,
    )

    course_report = adapt_verifier_rows(
        (
            VerifierRow(
                row_id="lesson-a:claim-1",
                lesson_id="lesson-a",
                claim_index=1,
                tier="VERBATIM",
                source_url="https://docs.example.test/guide",
                source_reference="official docs read 2026-10-22",
                source_read_date="2026-10-22",
                quote="must not escape",
            ),
        ),
        course_id="claude-course",
        course_revision="abc123",
        outcomes={
            "lesson-a:claim-1": ClaimVerificationState.VERBATIM_NOT_FOUND,
        },
        pages_fetched=1,
    )
    monkeypatch.setattr(
        portfolio_report,
        "run_claude_course_adapter",
        lambda *args, **kwargs: course_report,
    )

    result = portfolio_report.run_reference_portfolio_report(
        workspace=tmp_path,
        course_root=tmp_path / "course",
    )
    markdown = result.to_markdown()

    assert "Public course evidence" in markdown
    assert "`abc123`" in markdown
    assert "`lesson-a` claim `1`" in markdown
    assert "must not escape" not in markdown

    public_course = next(
        lane for lane in result.to_dict()["lanes"]
        if lane["lane_id"] == "public_course"
    )
    assert public_course["summary"]["review_packet"]["open_count"] == 1
