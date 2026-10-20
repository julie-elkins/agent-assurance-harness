import json
from pathlib import Path

from agent_reliability_lab.cli import main
from agent_reliability_lab.otlp import load_otlp_file, otlp_to_replay
from agent_reliability_lab.replay import run_replay


OTLP_PATH = Path(__file__).parents[2] / "examples" / "traces" / "otel-guarded.json"


def test_otlp_fixture_normalizes_and_passes_all_synthetic_scenarios():
    loaded = load_otlp_file(OTLP_PATH)

    assert loaded.refusal is None
    assert loaded.replay is not None
    report = run_replay(loaded.replay, source="synthetic-otlp")

    assert report.refusal is None
    assert report.agent_report is not None
    assert report.agent_report.passed is True
    assert len(report.agent_report.findings) == 6


def test_otlp_refuses_a_sensitive_attribute_before_normalization():
    data = json.loads(OTLP_PATH.read_text(encoding="utf-8"))
    span = data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["attributes"].append(
        {
            "key": "gen_ai.tool.call.arguments",
            "value": {"stringValue": "synthetic-sensitive-value"},
        }
    )

    loaded = otlp_to_replay(data)

    assert loaded.replay is None
    assert loaded.refusal is not None
    assert loaded.refusal.error == "sensitive_attribute_rejected"
    assert "synthetic-sensitive-value" not in loaded.refusal.message


def test_cli_evaluates_otlp_file_with_the_replay_gate(capsys):
    exit_code = main(
        [
            "--otlp-file",
            str(OTLP_PATH),
            "--json",
            "--fail-on-findings",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["refusal"] is None
    assert data["agent"]["passed"] is True
