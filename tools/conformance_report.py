"""Run an external adapter through the public conformance contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.conformance import run_adapter_conformance
from agent_reliability_lab.external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_RESPONSE_BYTES,
    SubprocessAdapter,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check one external JSONL adapter against the synthetic contract."
    )
    parser.add_argument("--agent-id", default="external-adapter")
    parser.add_argument(
        "--adapter-command",
        action="append",
        required=True,
        help="One adapter command argument; repeat once per argument.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero unless the adapter conforms.",
    )
    args = parser.parse_args(argv)

    report = run_adapter_conformance(
        SubprocessAdapter(
            agent_id=args.agent_id,
            command=tuple(args.adapter_command),
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
        )
    )
    serialized = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    if args.fail_on_findings and not report.conformance_passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
