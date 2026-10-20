"""Example adapter for any pack using the fixed declarative requirement prefixes."""

from __future__ import annotations

import json
import sys

from agent_reliability_lab.external import (
    adapter_run_to_dict,
    scenario_request_from_dict,
)
from agent_reliability_lab.recorder import TraceRecorder


def main() -> int:
    for line in sys.stdin:
        request = scenario_request_from_dict(json.loads(line))
        recorder = TraceRecorder(
            scenario_id=request.scenario_id,
            agent_id="custom-example",
        )
        for requirement in request.contract.requirements:
            prefix, value = requirement.requirement_id.split(":", 1)
            if prefix == "tool":
                recorder.record_tool_call(value)
                recorder.record_tool_result(
                    value,
                    "not_found",
                    result_id=f"{value}:result",
                )
            elif prefix == "abstain":
                recorder.record_abstention()
        print(
            json.dumps(adapter_run_to_dict(recorder.finish()), sort_keys=True),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
