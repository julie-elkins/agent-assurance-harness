import json
import subprocess
import sys

from agent_reliability_lab.claude_course_adapter import (
    ClaimVerificationState,
    VerifierRow,
    adapt_verifier_rows,
)
from agent_reliability_lab.public_course_review import (
    build_public_course_review_packet,
)


ROOT = __import__("pathlib").Path(__file__).parents[2]
TOOL = ROOT / "tools" / "public_course_review_adjudication.py"


def test_adjudication_cli_writes_safe_record(tmp_path):
    report = adapt_verifier_rows(
        (
            VerifierRow(
                row_id="lesson-a:claim-1",
                lesson_id="lesson-a",
                claim_index=1,
                tier="VERBATIM",
                source_url="https://docs.example.test/guide",
                source_reference="official docs read 2026-10-22",
                source_read_date="2026-10-22",
                quote="private claim text",
            ),
        ),
        course_id="claude-course",
        course_revision="abc123",
        outcomes={"lesson-a:claim-1": ClaimVerificationState.VERBATIM_NOT_FOUND},
        pages_fetched=1,
    )
    packet = build_public_course_review_packet(report).to_dict()
    packet_path = tmp_path / "packet.json"
    decisions_path = tmp_path / "decisions.json"
    output_path = tmp_path / "adjudication.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    decisions_path.write_text(
        json.dumps(
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
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--packet",
            str(packet_path),
            "--decisions",
            str(decisions_path),
            "--output",
            str(output_path),
            "--markdown",
            "--fail-on-open",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    record = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert record["decision"] == "adjudicated"
    assert record["open_count"] == 0
    assert "private claim text" not in result.stdout
