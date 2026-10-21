"""Refresh metadata for the fixed official AWS, Anthropic, and OpenAI sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.public_sources import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    refresh_public_sources,
)


def main(argv: list[str] | None = None) -> int:
    """Run the explicit, bounded metadata refresh."""

    parser = argparse.ArgumentParser(
        description=(
            "Hash fixed official documentation sources without storing their text."
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    report = refresh_public_sources(
        timeout_seconds=args.timeout_seconds,
        max_bytes=args.max_bytes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    args.output.write_text(serialized, encoding="utf-8")
    print(report.to_markdown() if args.markdown else serialized, end="")
    return int(args.fail_on_findings and not report.passed)


if __name__ == "__main__":
    raise SystemExit(main())
