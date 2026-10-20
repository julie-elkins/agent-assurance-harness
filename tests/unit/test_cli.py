import json

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
