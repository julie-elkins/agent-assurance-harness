import json
import os
import sys
import time
from pathlib import Path

import pytest

from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.external import (
    SubprocessAdapter,
    adapter_run_from_dict,
    adapter_run_to_dict,
    scenario_request_to_dict,
)
from agent_reliability_lab.models import Trace
from agent_reliability_lab.protocol import (
    AdapterRun,
    EventType,
    ObservableEvent,
    ScenarioRequest,
)
from agent_reliability_lab.runner import run_adapter_comparison
from agent_reliability_lab.scenarios import scenarios


def _request():
    scenario = scenarios()[0]
    return ScenarioRequest(
        scenario_id=scenario.scenario_id,
        task_label=scenario.title,
        available_tools=scenario.available_tools,
        contract=scenario.contract,
    )


def _script_path(name: str) -> str:
    return str(Path(__file__).parents[2] / "examples" / name)


def test_adapter_run_round_trip_omits_tool_arguments():
    run = AdapterRun(
        trace=Trace(
            scenario_id="synthetic",
            agent_id="external",
            claim="A claim.",
            abstained=True,
        ),
        events=(
            ObservableEvent(
                sequence=1,
                event_id="event-001",
                event_type=EventType.CLAIM,
                name="claim",
            ),
        ),
    )

    encoded = adapter_run_to_dict(run)
    decoded = adapter_run_from_dict(encoded)

    assert decoded.trace == run.trace
    assert "payload" not in json.dumps(encoded)


def test_subprocess_adapter_runs_example_command():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, _script_path("guarded_adapter.py")),
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is None
    assert result.trace is not None
    assert result.trace.agent_id == "external"


def test_subprocess_adapter_refuses_unknown_response_fields():
    adapter_run = {
        "trace": {
            "scenario_id": "synthetic",
            "agent_id": "external",
            "tool_calls": [],
            "claim": None,
            "answer": None,
            "abstained": True,
            "evidence_ids": [],
            "side_effects": [],
            "authorization_ids": [],
            "tool_output_flags": [],
            "payload": "must not cross the boundary",
        },
        "events": [],
    }

    try:
        adapter_run_from_dict(adapter_run)
    except ValueError as error:
        assert "unknown fields" in str(error)
    else:
        raise AssertionError("Unknown response field was accepted.")


def test_subprocess_adapter_times_out():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(
            sys.executable,
            "-c",
            "import time; time.sleep(2)",
        ),
        timeout_seconds=0.05,
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "adapter_timeout"


def test_subprocess_adapter_caps_stdout_before_parsing():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(
            sys.executable,
            "-c",
            "print('x' * 1000)",
        ),
        max_response_bytes=64,
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "response_too_large"


def test_subprocess_adapter_caps_stderr_without_echoing_diagnostics():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('x' * 1000); sys.stderr.flush()",
        ),
        max_stderr_bytes=64,
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "diagnostics_too_large"
    assert "x" * 20 not in result.refusal.message


def test_subprocess_adapter_rejects_invalid_sandbox_limits():
    for kwargs, error in (
        ({"max_stderr_bytes": 0}, "invalid_stderr_limit"),
        ({"max_memory_bytes": 0}, "invalid_memory_limit"),
    ):
        result = SubprocessAdapter(
            agent_id="external",
            command=(sys.executable, "-c", "pass"),
            **kwargs,
        ).run(
            _request(),
            environment=environment_for_scenario("tool-misuse"),
        )

        assert result.refusal is not None
        assert result.refusal.error == error


def test_subprocess_adapter_uses_explicit_working_directory(tmp_path):
    script = (
        "import json, os; "
        f"error = 'cwd-ok' if os.getcwd() == {str(tmp_path)!r} else 'cwd-bad'; "
        "print(json.dumps({'refusal': {'error': error, 'message': 'm', 'guidance': 'g'}}))"
    )
    result = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, "-c", script),
        working_directory=tmp_path,
    ).run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is not None
    assert result.refusal.error == "cwd-ok"


@pytest.mark.skipif(os.name != "posix", reason="process groups differ on Windows")
def test_subprocess_adapter_terminates_descendants_on_timeout(tmp_path):
    marker = tmp_path / "descendant-survived"
    child_code = (
        "import sys, time; time.sleep(0.4); "
        "open(sys.argv[1], 'w', encoding='utf-8').write('alive')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, {str(marker)!r}]); "
        "time.sleep(2)"
    )
    result = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, "-c", parent_code),
        timeout_seconds=0.05,
    ).run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    time.sleep(0.6)
    assert result.refusal is not None
    assert result.refusal.error == "adapter_timeout"
    assert not marker.exists()


def test_subprocess_adapter_refuses_empty_output():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, "-c", "pass"),
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is not None
    assert result.refusal.error == "invalid_jsonl_response"


def test_subprocess_adapter_refuses_extra_output_lines():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(
            sys.executable,
            "-c",
            "print('{}'); print('{}')",
        ),
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is not None
    assert result.refusal.error == "invalid_jsonl_response"


def test_subprocess_adapter_refuses_malformed_json():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, "-c", "print('not-json')"),
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is not None
    assert result.refusal.error == "malformed_adapter_response"


def test_subprocess_adapter_refuses_non_zero_exit():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, "-c", "raise SystemExit(3)"),
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is not None
    assert result.refusal.error == "adapter_exit_failed"


def test_subprocess_adapter_does_not_forward_secret_environment(monkeypatch):
    monkeypatch.setenv("AGENT_ASSURANCE_TEST_SECRET", "must-not-cross")
    script = (
        "import json, os; "
        "error = 'secret-forwarded' if os.getenv('AGENT_ASSURANCE_TEST_SECRET') "
        "else 'env-clean'; "
        "print(json.dumps({'refusal': {'error': error, 'message': 'm', 'guidance': 'g'}}))"
    )
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, "-c", script),
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is not None
    assert result.refusal.error == "env-clean"


def test_subprocess_adapter_does_not_interpret_shell_metacharacters(tmp_path):
    marker = tmp_path / "should-not-exist"
    script = (
        "import json; "
        "print(json.dumps({'refusal': {'error': 'safe', 'message': 'm', 'guidance': 'g'}}))"
    )
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, "-c", script, f"; touch {marker}"),
    )

    result = adapter.run(
        _request(),
        environment=environment_for_scenario("tool-misuse"),
    )

    assert result.refusal is not None
    assert result.refusal.error == "safe"
    assert not marker.exists()


def test_external_adapter_uses_the_same_report_shape_as_reference_adapter():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, _script_path("guarded_adapter.py")),
    )

    report = run_adapter_comparison(adapter, include_mutations=True)

    assert len(report.reports) == 1
    assert report.reports[0].passed is True
    assert len(report.contracts) == 7
    assert all(mutation.caught for mutation in report.mutation_tests)
