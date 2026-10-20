"""Synthetic adapter demonstrating the provider-neutral TraceRecorder integration."""

from __future__ import annotations

import argparse
import json
import sys

from agent_reliability_lab.environment import (
    SimulatedToolEnvironment,
    ToolObservation,
    environment_for_scenario,
)
from agent_reliability_lab.external import (
    adapter_run_to_dict,
    scenario_request_from_dict,
)
from agent_reliability_lab.protocol import AdapterRun, ScenarioRequest
from agent_reliability_lab.recorder import TraceRecorder
from agent_reliability_lab.replay import REPLAY_VERSION, ReplayCase, ReplayFile
from agent_reliability_lab.scenarios import scenarios


AGENT_ID = "external"


def _record_observation(
    recorder: TraceRecorder,
    observation: ToolObservation,
) -> None:
    """Map synthetic observable metadata into the recorder boundary."""

    recorder.record_tool_call(observation.tool_name)
    recorder.record_tool_result(
        observation.tool_name,
        observation.result_status,
        result_id=observation.result_id,
        output_flags=observation.output_flags,
    )
    if observation.authorization_present:
        recorder.record_authorization("authorization:approval")
    if observation.side_effect_attempted is not None:
        recorder.record_side_effect(observation.side_effect_attempted)


def _record_guarded_run(
    scenario_id: str,
    environment: SimulatedToolEnvironment,
) -> AdapterRun:
    """Run one synthetic guarded policy through TraceRecorder."""

    recorder = TraceRecorder(scenario_id=scenario_id, agent_id=AGENT_ID)
    if scenario_id == "tool-misuse":
        _record_observation(recorder, environment.invoke("lookup_policy"))
        recorder.record_claim("claim:policy_checked")
        recorder.record_answer("answer:no_policy_evidence")
        recorder.record_abstention()
    elif scenario_id == "false-completion":
        _record_observation(recorder, environment.invoke("check_inventory"))
        _record_observation(recorder, environment.invoke("check_shipping"))
        recorder.record_claim("claim:all_checks_complete")
        recorder.record_answer("answer:ready_to_proceed")
    elif scenario_id == "inappropriate-answer":
        _record_observation(recorder, environment.invoke("lookup_policy"))
        recorder.record_claim("claim:evidence_insufficient")
        recorder.record_abstention()
    elif scenario_id == "unauthorized-side-effect":
        recorder.record_claim("claim:authorization_required")
        recorder.record_abstention()
    elif scenario_id == "misleading-tool-output":
        _record_observation(recorder, environment.invoke("lookup_catalog"))
        recorder.record_claim("claim:tool_output_is_data")
        recorder.record_abstention()
    else:
        recorder.record_claim(f"claim:unknown_scenario:{scenario_id}")
    return recorder.finish()


def _run_request(request: ScenarioRequest) -> AdapterRun:
    """Record one JSONL request using only synthetic environment metadata."""

    return _record_guarded_run(
        request.scenario_id,
        environment_for_scenario(request.scenario_id),
    )


def _replay_file() -> ReplayFile:
    """Generate a complete synthetic replay through TraceRecorder."""

    cases = tuple(
        ReplayCase(
            scenario_id=scenario.scenario_id,
            response=_record_guarded_run(
                scenario.scenario_id,
                environment_for_scenario(scenario.scenario_id),
            ),
        )
        for scenario in scenarios()
    )
    return ReplayFile(
        replay_version=REPLAY_VERSION,
        agent_id=AGENT_ID,
        cases=cases,
    )


def _jsonl_main() -> int:
    for line in sys.stdin:
        request = scenario_request_from_dict(json.loads(line))
        print(
            json.dumps(adapter_run_to_dict(_run_request(request)), sort_keys=True),
            flush=True,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Emit either one complete replay file or the adapter JSONL protocol."""

    parser = argparse.ArgumentParser(
        description="Run the synthetic TraceRecorder integration example."
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Generate one complete identifier-only replay file to stdout.",
    )
    args = parser.parse_args(argv)
    if args.replay:
        print(json.dumps(_replay_file().to_dict(), indent=2, sort_keys=True))
        return 0
    return _jsonl_main()


if __name__ == "__main__":
    raise SystemExit(main())
