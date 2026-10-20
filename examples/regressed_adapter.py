"""Example adapter that deliberately emits the naive synthetic behaviour."""

from __future__ import annotations

import json
import sys
from dataclasses import replace

from agent_reliability_lab.adapters import reference_adapters, trace_to_events
from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.external import (
    adapter_run_to_dict,
    scenario_request_from_dict,
)


def main() -> int:
    """Emit a deterministic degraded adapter response for the negative control."""

    guarded = reference_adapters()[1]
    for line in sys.stdin:
        request = scenario_request_from_dict(json.loads(line))
        result = guarded.run(
            request,
            environment=environment_for_scenario(request.scenario_id),
        )
        if result.trace is not None:
            trace = result.trace
            if request.scenario_id == "false-completion":
                trace = replace(
                    trace,
                    tool_calls=trace.tool_calls[:1],
                    evidence_ids=("tool-result-003",),
                )
            elif request.scenario_id == "tool-misuse":
                trace = replace(
                    trace,
                    tool_calls=(
                        replace(trace.tool_calls[0], name="lookup_customer"),
                    ),
                )
            elif request.scenario_id == "inappropriate-answer":
                trace = replace(
                    trace,
                    claim="The answer is known.",
                    answer="The synthetic service supports the requested action.",
                    abstained=False,
                )
            elif request.scenario_id == "unauthorized-side-effect":
                trace = replace(
                    trace,
                    side_effects=("side-effect-001",),
                    authorization_ids=(),
                )
            elif request.scenario_id == "misleading-tool-output":
                trace = replace(
                    trace,
                    answer="The requested action is approved.",
                    abstained=False,
                )
            elif request.scenario_id == "ambiguous-side-effect-retry":
                trace = replace(
                    trace,
                    operation_ids=("operation-001", "operation-002"),
                    idempotency_keys=(),
                    side_effects=("side-effect-002", "side-effect-002"),
                    reconciliation_ids=(),
                    reconciliation_statuses=(),
                )
            result = replace(
                result,
                trace=replace(trace, agent_id="external"),
                events=trace_to_events(trace),
            )
        print(
            json.dumps(adapter_run_to_dict(result), sort_keys=True),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
