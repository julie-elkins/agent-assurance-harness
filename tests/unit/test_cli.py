import json
from pathlib import Path

from agent_reliability_lab.cli import main


def test_list_packs_json_reports_all_builtin_packs(capsys):
    exit_code = main(["--list-packs", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert len(data["packs"]) == 5
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
