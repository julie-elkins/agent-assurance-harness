"""Run the offline provider adapter assurance lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.provider_assurance import (
    ProviderAssuranceReport,
    run_provider_assurance,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run mocked OpenAI- and Anthropic-shaped adapters through the "
            "shared assurance path and catch an over-budget negative control."
        )
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    report: ProviderAssuranceReport = run_provider_assurance()
    data = report.to_dict()
    serialized = (
        report.to_markdown()
        if args.markdown
        else json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    if args.fail_on_findings and not report.passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
