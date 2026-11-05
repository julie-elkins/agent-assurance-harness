"""Run the synthetic provider shadow-reauthorization demonstration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.run_manifest import load_current_revisions
from agent_reliability_lab.shadow_reauthorization import (
    ShadowReauthorizationReport,
    load_shadow_reauthorization_fixture,
    run_shadow_reauthorization,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "examples" / "shadow-reauthorization" / "fixture.json"
DEFAULT_CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"
DEFAULT_CHANGED = ROOT / "examples" / "run-manifest" / "changed-revisions.json"


def main(argv: list[str] | None = None) -> int:
    """Run the provider-shaped fixture and emit JSON or Markdown."""

    parser = argparse.ArgumentParser(
        description=(
            "Compare provider-shaped shadow receipts against current and changed "
            "revision maps without provider calls or real side effects."
        )
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--current-revisions", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--changed-revisions", type=Path, default=DEFAULT_CHANGED)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    try:
        proposals = load_shadow_reauthorization_fixture(
            args.fixture,
            repository_root=ROOT,
        )
        report: ShadowReauthorizationReport = run_shadow_reauthorization(
            proposals,
            load_current_revisions(str(args.current_revisions)),
            load_current_revisions(str(args.changed_revisions)),
        )
        data = report.to_dict()
        serialized = (
            report.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_findings and not report.passed)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "shadow_reauthorization_version": 1,
            "passed": False,
            "results": [],
            "diagnostics": {
                "refusal": "shadow_reauthorization_input_invalid",
                "source": type(error).__name__,
                "what_it_does_not_show": (
                    "It does not show fixture content, provider output, "
                    "credentials, or real tool execution."
                ),
            },
        }
        serialized = (
            "## Shadow reauthorization\n\n"
            "- **Decision:** `BLOCKED`\n"
            "- **Required action:** Repair the synthetic fixture or revision maps.\n"
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
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
