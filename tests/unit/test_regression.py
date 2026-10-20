import json
from pathlib import Path

from agent_reliability_lab.regression import compare_replay_files
from agent_reliability_lab.replay import load_replay_file


REPLAY_PATH = Path(__file__).parents[2] / "examples" / "traces" / "guarded.json"


def _candidate_data() -> dict[str, object]:
    data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    data["harness_change"] = {
        "change_id": "candidate-guardrails-2026-10-20",
        "components": ["guardrails"],
    }
    return data


def test_baseline_compared_with_itself_passes(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(REPLAY_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    report = compare_replay_files(path, path)

    assert report.refusal is None
    assert report.failed is False
    assert report.findings == ()
    assert report.candidate_change is not None
    assert report.candidate_change.components == (
        "guardrails",
        "tool_guidance",
    )


def test_safety_regression_is_blocking_and_names_changed_component(tmp_path):
    data = _candidate_data()
    false_completion = data["runs"][1]["response"]["trace"]
    false_completion["tool_calls"] = false_completion["tool_calls"][:1]
    false_completion["evidence_ids"] = ["tool-result-003"]
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = compare_replay_files(REPLAY_PATH, path)

    assert report.refusal is None
    assert report.failed is True
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.category == "evidence_loss"
    assert finding.blocking is True
    assert finding.changed_components == ("guardrails",)
    assert finding.newly_missing_evidence == ("successful_tool:check_shipping",)


def test_task_outcome_regression_is_reported_without_blocking(tmp_path):
    data = _candidate_data()
    tool_misuse = data["runs"][0]["response"]["trace"]
    tool_misuse["tool_calls"][0]["name"] = "lookup_customer"
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = compare_replay_files(REPLAY_PATH, path)

    assert report.refusal is None
    assert report.failed is False
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.category == "new_failure"
    assert finding.blocking is False
    assert finding.dimension.value == "task_outcome"


def test_comparison_refuses_missing_candidate_manifest(tmp_path):
    data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    del data["harness_change"]
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = compare_replay_files(REPLAY_PATH, path)

    assert report.refusal is not None
    assert report.refusal.error == "harness_change_manifest_required"


def test_manifest_rejects_free_form_component_text(tmp_path):
    data = _candidate_data()
    data["harness_change"]["components"] = ["raw prompt text"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_replay_file(path)

    assert loaded.replay is None
    assert loaded.refusal is not None
    assert loaded.refusal.error == "invalid_replay_file"
