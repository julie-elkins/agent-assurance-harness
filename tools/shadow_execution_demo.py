"""Run the offline synthetic shadow-execution demonstration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.shadow_execution import (
    ShadowExecutionReport,
    load_shadow_cases,
    run_shadow_cases,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "examples" / "shadow-execution" / "manifest.json"


def main(argv: list[str] | None = None) -> int:
    """Run the fixture and emit JSON or reviewer-facing Markdown."""

    parser = argparse.ArgumentParser(
        description=(
            "Compare synthetic intended and observed effects without executing "
            "external tools or writing to a real system."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)

    try:
        cases = load_shadow_cases(args.manifest)
        report: ShadowExecutionReport = run_shadow_cases(cases)
        data = report.to_dict()
        serialized = (
            report.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_block and not report.passed)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "shadow_execution_version": 1,
            "passed": False,
            "refusal": {
                "error": "shadow_execution_refused",
                "message": "The shadow execution fixture could not be evaluated.",
                "guidance": (
                    "Repair the synthetic manifest before running the demo again."
                ),
                "source": type(error).__name__,
            },
            "diagnostics": {
                "warnings": [
                    "A refusal is a blocked result, not a passing empty result."
                ],
                "what_it_does_not_show": (
                    "It does not show raw fixture content or execute an external action."
                ),
            },
        }
        serialized = (
            "## Shadow execution\n\n"
            "- **Decision:** BLOCKED\n"
            "- **Reason:** `shadow-execution-refused`\n"
        )
        exit_code = 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
