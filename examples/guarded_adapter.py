"""Example JSONL adapter for the public Agent Assurance Harness."""

from __future__ import annotations

import json
import sys
from dataclasses import replace

from agent_reliability_lab.adapters import reference_adapters
from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.external import (
    adapter_run_to_dict,
    scenario_request_from_dict,
)


def main() -> int:
    guarded = reference_adapters()[1]
    for line in sys.stdin:
        request = scenario_request_from_dict(json.loads(line))
        result = guarded.run(
            request,
            environment=environment_for_scenario(request.scenario_id),
        )
        if result.trace is not None:
            result = replace(
                result,
                trace=replace(result.trace, agent_id="external"),
            )
        print(json.dumps(adapter_run_to_dict(result), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
