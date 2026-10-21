"""JSONL adapter for the technical content assurance reference agent."""

from __future__ import annotations

import json
import sys

from agent_reliability_lab.content_assurance import ContentAssuranceAdapter
from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.external import (
    adapter_run_to_dict,
    scenario_request_from_dict,
)


def main() -> int:
    """Run each supplied content pack through the reference agent."""

    adapter = ContentAssuranceAdapter()
    for line in sys.stdin:
        request = scenario_request_from_dict(json.loads(line))
        result = adapter.run(
            request,
            environment=environment_for_scenario("tool-misuse"),
        )
        print(json.dumps(adapter_run_to_dict(result), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
