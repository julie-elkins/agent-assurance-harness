import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.course_doctor import (
    reference_course_doctor_cases,
)


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "course_doctor_report.py"


def test_course_doctor_report_is_metadata_only(tmp_path):
    output = tmp_path / "course-doctor.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--workspace",
            str(tmp_path / "workspace"),
            "--output",
            str(output),
            "--markdown",
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["course_doctor_version"] == 2
    assert report["passed"] is True
    assert report["counts"]["requested"] == 5
    assert report["counts"]["packets_emitted"] == 5
    assert report["counts"]["not_reviewed"] == 0
    assert len(reference_course_doctor_cases()) == 5
    assert "Approved technical guidance fixture" not in result.stdout


def test_course_doctor_cli_writes_local_index_separately(tmp_path):
    case = next(
        case
        for case in reference_course_doctor_cases()
        if case.course_id == "course-pipeline-stale-source"
    )
    pipeline = case.request.freshness_request.pipeline_request
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "lesson.md").write_bytes(pipeline.source_bytes)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "courses": [
                    {
                        "course_id": case.course_id,
                        "course_revision": case.request.course_revision,
                        "source_path": "lesson.md",
                        "case_id": pipeline.case_id,
                        "artifact_id": pipeline.artifact_id,
                        "artifact_revision": pipeline.artifact_revision,
                        "artifact_digest": pipeline.artifact_digest,
                        "reuse_key": pipeline.reuse_key,
                        "source_id": pipeline.source_id,
                        "authority": pipeline.authority,
                        "source_url": pipeline.source_url,
                        "age_seconds": pipeline.age_seconds,
                        "claims": [
                            {
                                "claim_id": pipeline.claims[0].claim_id,
                                "section_id": pipeline.claims[0].section_id,
                                "support_status": pipeline.claims[0].support_status,
                                "line_start": 12,
                                "line_end": 18,
                            }
                        ],
                        "approved_source_ids": list(
                            pipeline.approved_source_ids
                        ),
                        "max_age_seconds": pipeline.max_age_seconds,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "course-doctor.json"
    index = tmp_path / "local-index.json"

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--manifest",
            str(manifest),
            "--source-root",
            str(source_root),
            "--workspace",
            str(tmp_path / "workspace"),
            "--output",
            str(output),
            "--local-index-output",
            str(index),
        ],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )

    public_report = output.read_text(encoding="utf-8")
    local_index = json.loads(index.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert "lesson.md" not in public_report
    assert local_index["entries"][0]["source_path"] == "lesson.md"
    assert local_index["entries"][0]["line_start"] == 12
    assert local_index["entries"][0]["line_end"] == 18
