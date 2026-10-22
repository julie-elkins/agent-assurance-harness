"""Synthetic developer-workflow adapter for the portfolio assurance demo.

The adapter is deliberately contract-driven: it records only the evidence identifiers
declared by the pack. It does not edit a repository, execute a shell command, or send
provider prompts. ``--mode degraded`` omits the security-check evidence for one
synthetic task so the negative control must be blocked.
"""

from __future__ import annotations

import argparse
import json
import sys

from agent_reliability_lab.external import (
    adapter_run_to_dict,
    scenario_request_from_dict,
)
from agent_reliability_lab.recorder import TraceRecorder


ACTION_DIGEST = (
    "sha256:"
    "9d8a7b6c5e4f3029182736455463728190abcdefabcdefabcdefabcdefabcdef"
)


def _record_requirement(
    recorder: TraceRecorder,
    requirement,
    *,
    seen_tools: set[str],
    requirements,
    authorization_recorded: set[str],
) -> None:
    prefix, value = requirement.requirement_id.split(":", 1)
    if prefix in {"tool", "successful_tool"}:
        if value in seen_tools:
            return
        recorder.record_tool_call(value)
        recorder.record_tool_result(
            value,
            "ok",
            result_id=f"evidence:{value}",
            output_flags=(
                ("instruction_like",)
                if any(
                    item.requirement_id == "output:treat-as-data"
                    for item in requirements
                )
                else ()
            ),
            source=requirement.source,
            age_seconds=(
                requirement.max_age_seconds / 2
                if requirement.max_age_seconds is not None
                else None
            ),
        )
        seen_tools.add(value)
        return
    if prefix == "abstain":
        recorder.record_abstention(reason_id=value)
        return
    if requirement.requirement_id == "output:treat-as-data":
        recorder.record_tool_output_flag("instruction_like")
        return
    if prefix == "authorization":
        if "approval" in authorization_recorded:
            return
        recorder.record_authorization(
            "authorization:approval",
            operation_id="operation:release-001",
            action_digest=ACTION_DIGEST,
        )
        authorization_recorded.add("approval")
        return
    if prefix == "action-digest":
        recorder.record_action_digest(ACTION_DIGEST)
        return
    if requirement.requirement_id == "side-effect:operation-id":
        recorder.record_operation_id("operation:release-001")
        recorder.record_operation_id("operation:release-001")
        return
    if requirement.requirement_id == "side-effect:idempotency-key":
        recorder.record_idempotency_key("idempotency:release-001")
        recorder.record_idempotency_key("idempotency:release-001")
        return
    if requirement.requirement_id == "side-effect:no-duplicate":
        recorder.record_side_effect("side-effect:release-001")
        return
    if requirement.requirement_id == "reconciliation:confirmed":
        recorder.record_reconciliation("reconciliation:release-001", "confirmed")


def _run(request, *, mode: str):
    recorder = TraceRecorder(
        scenario_id=request.scenario_id,
        agent_id=f"developer-workflow-{mode}",
    )
    seen_tools: set[str] = set()
    authorization_recorded: set[str] = set()
    for requirement in request.contract.requirements:
        if (
            mode == "degraded"
            and request.scenario_id == "developer-green-but-unaudited"
            and requirement.requirement_id
            in {
                "successful_tool:run_security_check",
                "tool:run_security_check",
            }
        ):
            continue
        _record_requirement(
            recorder,
            requirement,
            seen_tools=seen_tools,
            requirements=request.contract.requirements,
            authorization_recorded=authorization_recorded,
        )
    return recorder.finish()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("guarded", "degraded"), default="guarded")
    args = parser.parse_args(argv)

    for line in sys.stdin:
        request = scenario_request_from_dict(json.loads(line))
        print(
            json.dumps(
                adapter_run_to_dict(_run(request, mode=args.mode)),
                sort_keys=True,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
