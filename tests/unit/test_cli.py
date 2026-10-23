import json
from pathlib import Path

from agent_reliability_lab.cli import main


def test_list_packs_json_reports_all_builtin_packs(capsys):
    exit_code = main(["--list-packs", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert len(data["packs"]) == 10
    assert data["refusals"] == []


def test_list_packs_reports_invalid_pack(tmp_path, capsys):
    (tmp_path / "invalid.json").write_text('{"payload": "not allowed"}', encoding="utf-8")

    exit_code = main(["--list-packs", "--pack-directory", str(tmp_path), "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 1
    assert data["packs"] == []
    assert data["refusals"][0]["error"] == "invalid_scenario_pack"


def test_replay_file_passes_with_fail_on_findings(capsys):
    replay_path = (
        Path(__file__).parents[2] / "examples" / "traces" / "guarded.json"
    )

    exit_code = main(
        [
            "--replay-file",
            str(replay_path),
            "--json",
            "--fail-on-findings",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["refusal"] is None
    assert data["agent"]["passed"] is True


def test_replay_file_refusal_has_nonzero_exit(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text('{"replay_version": 1, "agent_id": "x", "runs": []}', encoding="utf-8")

    exit_code = main(["--replay-file", str(path), "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 1
    assert data["refusal"]["error"] == "invalid_replay_file"


def test_compare_replay_passes_with_fail_on_findings(capsys):
    replay_path = (
        Path(__file__).parents[2] / "examples" / "traces" / "guarded.json"
    )

    exit_code = main(
        [
            "--compare-replay",
            str(replay_path),
            str(replay_path),
            "--json",
            "--fail-on-findings",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["passed"] is True
    assert data["findings"] == []


def test_mock_provider_check_passes_with_fail_on_findings(capsys):
    exit_code = main(
        [
            "--mock-provider",
            "all",
            "--json",
            "--fail-on-findings",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert [report["agent_id"] for report in data["reports"]] == [
        "anthropic-mock",
        "openai-mock",
    ]
    assert all(report["passed"] for report in data["reports"])


def test_live_provider_requires_explicit_budgets_before_network(capsys):
    exit_code = main(["--live-provider", "openai"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--scenario-id" in captured.err
    assert "OPENAI_API_KEY" not in captured.err


def test_live_provider_refusal_is_nonzero_without_network_opt_in(capsys):
    exit_code = main(
        [
            "--live-provider",
            "openai",
            "--scenario-id",
            "unauthorized-side-effect",
            "--model",
            "synthetic-model",
            "--max-requests",
            "1",
            "--max-output-tokens",
            "64",
            "--max-elapsed-seconds",
            "5",
            "--max-estimated-cost-usd",
            "0.01",
            "--estimated-cost-usd-per-request",
            "0.001",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 1
    assert data["reports"][0]["findings"][0]["status"] == "refused"
    assert data["reports"][0]["findings"][0]["message"] == (
        "Live provider execution requires explicit network opt-in."
    )
