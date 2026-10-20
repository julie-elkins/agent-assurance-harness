"""Run the offline provider contract drift gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.provider_contract import (
    ProviderContractReport,
    run_provider_contract_assurance,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "examples" / "provider-contract-manifest.json"
DEFAULT_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "provider_contracts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fingerprint reviewed OpenAI- and Anthropic-shaped response contracts "
            "and require safe refusal of negative fixtures."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args(argv)

    try:
        report: ProviderContractReport = run_provider_contract_assurance(
            args.manifest,
            args.fixture_root,
        )
        data = report.to_dict()
        serialized = (
            report.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_drift and not report.passed)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "provider_contract_version": 1,
            "passed": False,
            "refusal": {
                "error": "provider_contract_refused",
                "message": "The provider contract gate could not be completed.",
                "guidance": (
                    "Repair the manifest or checked-in fixtures before retrying."
                ),
                "source": type(error).__name__,
            },
        }
        serialized = (
            "## Provider contract drift gate\n\n"
            "- **Decision:** BLOCKED\n"
            "- **Reason:** `provider-contract-refused`\n"
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
