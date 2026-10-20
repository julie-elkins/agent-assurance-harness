"""Run an external adapter against caller-supplied declarative packs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.conformance import run_custom_pack_conformance
from agent_reliability_lab.external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MAX_STDERR_BYTES,
    SubprocessAdapter,
)
from agent_reliability_lab.packs import load_pack_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an external adapter against declarative scenario packs."
    )
    parser.add_argument("--pack-directory", type=Path, required=True)
    parser.add_argument("--agent-id", default="external-adapter")
    parser.add_argument("--adapter-command", action="append", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_ADAPTER_TIMEOUT_SECONDS)
    parser.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    parser.add_argument("--max-stderr-bytes", type=int, default=DEFAULT_MAX_STDERR_BYTES)
    parser.add_argument("--max-memory-bytes", type=int, default=DEFAULT_MAX_MEMORY_BYTES)
    parser.add_argument("--adapter-working-directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    results = load_pack_directory(args.pack_directory)
    refusals = [
        result.refusal.to_dict()
        for result in results
        if result.refusal is not None
    ]
    packs = tuple(result.pack for result in results if result.pack is not None)
    if refusals:
        report: dict[str, object] = {
            "report_version": 2,
            "conformance_id": "custom-pack-conformance-v2",
            "pack_count": 0,
            "passed": False,
            "refusals": refusals,
        }
        exit_code = 1
    else:
        result = run_custom_pack_conformance(
            SubprocessAdapter(
                agent_id=args.agent_id,
                command=tuple(args.adapter_command),
                timeout_seconds=args.timeout_seconds,
                max_response_bytes=args.max_response_bytes,
                max_stderr_bytes=args.max_stderr_bytes,
                max_memory_bytes=args.max_memory_bytes,
                working_directory=args.adapter_working_directory,
            ),
            packs,
        )
        report = result.to_dict()
        exit_code = 1 if args.fail_on_findings and not result.passed else 0

    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
