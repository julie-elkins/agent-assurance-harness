"""Run the synthetic developer-workflow assurance portfolio lane."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.conformance import run_custom_pack_conformance
from agent_reliability_lab.external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MAX_STDERR_BYTES,
    SubprocessAdapter,
)
from agent_reliability_lab.pack_provenance import pack_set_sha256
from agent_reliability_lab.packs import load_pack_directory


ROOT = Path(__file__).parents[1]
DEFAULT_PACK_DIRECTORY = ROOT / "examples" / "developer-workflow-packs"
ADAPTER = ROOT / "examples" / "developer_workflow_adapter.py"


def _run_mode(
    packs,
    *,
    mode: str,
    timeout_seconds: float,
    max_response_bytes: int,
    max_stderr_bytes: int,
    max_memory_bytes: int,
):
    return run_custom_pack_conformance(
        SubprocessAdapter(
            agent_id=f"developer-workflow-{mode}",
            command=(
                sys.executable,
                str(ADAPTER),
                "--mode",
                mode,
            ),
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_stderr_bytes=max_stderr_bytes,
            max_memory_bytes=max_memory_bytes,
            working_directory=ROOT,
        ),
        packs,
    )


def _report(
    packs,
    *,
    guarded,
    degraded,
) -> dict[str, object]:
    negative_control_caught = not degraded.passed
    return {
        "report_version": 1,
        "report_kind": "developer-workflow-assurance-v1",
        "decision": "pass" if guarded.passed and negative_control_caught else "blocked",
        "offline": True,
        "synthetic_only": True,
        "raw_payloads_included": False,
        "provider_output_included": False,
        "live_repository_execution": False,
        "pack_count": len(packs),
        "pack_set_sha256": pack_set_sha256(packs),
        "guarded_reference": guarded.to_dict(),
        "degraded_negative_control": {
            "agent_id": degraded.agent_id,
            "expected": "blocked",
            "caught": negative_control_caught,
            "passed": degraded.passed,
            "trace_count": degraded.trace_count,
            "refusal_count": degraded.refusal_count,
            "dimensions": [dict(item) for item in degraded.dimensions],
            "pack_count": len(degraded.pack_ids),
        },
        "negative_control": {
            "scenario_id": "developer-green-but-unaudited",
            "failure_class": "missing_required_verification_evidence",
            "expected_decision": "blocked",
            "caught": negative_control_caught,
        },
        "limits": [
            "The packs use synthetic task identifiers and synthetic tool results.",
            "The lane checks observable evidence contracts; it does not prove patch correctness.",
            "No model, repository checkout, provider credential, or live tool is used.",
        ],
    }


def _markdown(report: dict[str, object]) -> str:
    if "guarded_reference" not in report:
        return "\n".join(
            [
                "# Developer workflow assurance",
                "",
                "- **Decision:** `BLOCKED`",
                f"- **Pack loader refusals:** `{len(report.get('refusals', []))}`",
                "",
                "The pack set could not be validated, so the lane stopped before "
                "running an adapter.",
                "",
            ]
        )
    guarded = report["guarded_reference"]
    negative = report["degraded_negative_control"]
    decision = str(report["decision"]).upper()
    return "\n".join(
        [
            "# Developer workflow assurance",
            "",
            f"- **Decision:** `{decision}`",
            f"- **Synthetic packs checked:** `{report['pack_count']}`",
            f"- **Guarded reference:** `{'PASS' if guarded['passed'] else 'BLOCKED'}`",
            f"- **Green-but-unaudited negative control caught:** "
            f"`{'YES' if negative['caught'] else 'NO'}`",
            "",
            "The negative control represents a plausible green change that is blocked "
            "because required security or dependency evidence is missing.",
            "",
            "This lane checks observable workflow evidence, not source-code correctness. "
            "It runs offline and emits identifiers, counts, and hashes only.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the synthetic developer-workflow assurance lane."
    )
    parser.add_argument("--pack-directory", type=Path, default=DEFAULT_PACK_DIRECTORY)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
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
    parser.add_argument(
        "--max-stderr-bytes",
        type=int,
        default=DEFAULT_MAX_STDERR_BYTES,
    )
    parser.add_argument(
        "--max-memory-bytes",
        type=int,
        default=DEFAULT_MAX_MEMORY_BYTES,
    )
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
            "report_version": 1,
            "report_kind": "developer-workflow-assurance-v1",
            "decision": "blocked",
            "offline": True,
            "synthetic_only": True,
            "pack_count": len(packs),
            "refusals": refusals,
        }
    else:
        guarded = _run_mode(
            packs,
            mode="guarded",
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
            max_stderr_bytes=args.max_stderr_bytes,
            max_memory_bytes=args.max_memory_bytes,
        )
        degraded = _run_mode(
            packs,
            mode="degraded",
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
            max_stderr_bytes=args.max_stderr_bytes,
            max_memory_bytes=args.max_memory_bytes,
        )
        report = _report(packs, guarded=guarded, degraded=degraded)

    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(_markdown(report) if args.markdown else serialized, end="")

    if args.fail_on_findings and report.get("decision") != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
