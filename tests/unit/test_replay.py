import json
from pathlib import Path

from agent_reliability_lab.adapters import reference_adapters
from agent_reliability_lab.replay import (
    HarnessChangeManifest,
    load_replay_file,
    run_adapter_replay,
    run_replay_file,
)


REPLAY_PATH = Path(__file__).parents[2] / "examples" / "traces" / "guarded.json"


def test_guarded_fixture_replays_as_passing():
    report = run_replay_file(REPLAY_PATH)

    assert report.refusal is None
    assert report.agent_report is not None
    assert report.agent_report.passed is True
    assert len(report.agent_report.findings) == 9


def test_adapter_replay_covers_all_builtin_scenarios_in_memory():
    replay = run_adapter_replay(
        reference_adapters()[1],
        harness_change=HarnessChangeManifest(
            change_id="candidate-guardrails-2026-10-20",
            components=("guardrails",),
        ),
    )

    assert len(replay.cases) == 9
    assert replay.harness_change is not None
    assert replay.harness_change.components == ("guardrails",)
    assert all(case.response.trace is not None for case in replay.cases)


def test_mutated_replay_fails_the_gate(tmp_path):
    data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    data["runs"][0]["response"]["trace"]["tool_calls"][0]["name"] = "lookup_customer"
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = run_replay_file(path)

    assert report.refusal is None
    assert report.failed is True
    assert report.agent_report is not None
    assert report.agent_report.findings[0].status.value == "failed"


def test_replay_refuses_missing_scenario_coverage(tmp_path):
    data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    data["runs"] = data["runs"][:-1]
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = run_replay_file(path)

    assert report.refusal is not None
    assert report.refusal.error == "incomplete_replay_coverage"
    assert report.failed is True


def test_replay_refuses_unknown_top_level_fields(tmp_path):
    data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    data["payload"] = "not allowed"
    path = tmp_path / "unknown-field.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_replay_file(path)

    assert loaded.replay is None
    assert loaded.refusal is not None
    assert loaded.refusal.error == "invalid_replay_file"
