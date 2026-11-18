import json
from pathlib import Path

from agent_reliability_lab.atif_conformance import run_atif_conformance


FIXTURE_DIR = Path(__file__).parents[2] / "examples" / "atif-conformance"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_metadata_only_atif_summary_passes_without_turning_task_outcome_into_evidence():
    report = run_atif_conformance(_fixture("positive.json"))

    assert report.conformance_passed
    assert report.semantic_outcome_observed
    assert report.to_dict()["diagnostics"]["task_correctness"] == "separate"


def test_muse_ember_synthetic_track_uses_the_same_evidence_contract():
    report = run_atif_conformance(_fixture("muse-ember-synthetic.json"))

    assert report.conformance_passed
    assert report.source_id == "muse-ember"


def test_harbor_adapter_post_merge_fixture_passes_the_same_contract():
    report = run_atif_conformance(_fixture("harbor-adapter-v1.2.json"))

    assert report.conformance_passed
    assert report.source_id == "harbor"
    assert report.schema_version == "ATIF-v1.2"


def test_missing_trajectory_artifact_is_refused_even_when_terminal_status_says_completed():
    report = run_atif_conformance(_fixture("missing-artifact.json"))

    assert not report.conformance_passed
    assert report.refusal_code == "trajectory_artifact_not_observed"
    assert "completed_without_observed_artifact" in {
        check.reason for check in report.checks
    }


def test_partial_event_linkage_is_refused_when_tool_calls_are_reported():
    report = run_atif_conformance(_fixture("partial-linkage.json"))

    assert not report.conformance_passed
    assert report.refusal_code == "event_linkage_incomplete"


def test_raw_content_field_is_refused_without_echoing_the_field_or_value():
    value = _fixture("positive.json")
    value["provider_response"] = "synthetic content that must not escape"

    report = run_atif_conformance(value)
    serialized = json.dumps(report.to_dict())

    assert report.refusal_code == "raw_content_refused"
    assert "provider_response" not in serialized
    assert "synthetic content" not in serialized


def test_invalid_digest_is_refused_without_an_exception():
    value = _fixture("positive.json")
    value["trajectory_digest"] = "not-a-digest"

    report = run_atif_conformance(value)

    assert report.refusal_code == "invalid_summary"
    assert report.status == "refused"
