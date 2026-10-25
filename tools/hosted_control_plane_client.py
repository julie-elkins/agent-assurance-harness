"""Submit synthetic run manifests to the hosted assurance control plane.

The command prints a bounded decision view to stdout and sends diagnostics to stderr.
It is a local integration client, not a provider gateway: provider-shaped submissions
use the checked-in synthetic manifest and never read provider credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from agent_reliability_lab.hosted_client import (
    HostedControlPlaneClient,
    build_local_run,
)


def _markdown(data: dict[str, object]) -> str:
    lines = ["## Hosted assurance client", ""]
    for result in data["results"]:
        assert isinstance(result, dict)
        provider = result.get("provider", "unknown")
        lines.append(f"### Provider: `{provider}`")
        if "refusal" in result:
            lines.append("- **Decision:** `BLOCKED`")
            lines.append(
                f"- **Refusal:** `{result['refusal']['error']}`"
            )
            continue
        latest = result.get("latest", {})
        assert isinstance(latest, dict)
        lines.append(f"- **Decision:** `{str(latest.get('status', 'missing')).upper()}`")
        lines.append(
            "- **Supports target decision:** "
            f"`{str(latest.get('supports_decision', False)).lower()}`"
        )
        changed = latest.get("changed_dependencies", [])
        lines.append(
            "- **Changed dependencies:** "
            f"{', '.join(str(item) for item in changed) or 'none'}"
        )
    lines.extend(
        [
            "",
            "The client sends validated metadata and digests only; it does not send "
            "prompts, tool payloads, provider output, or credentials.",
            "",
        ]
    )
    return "\n".join(lines)


def _provider_choices(value: str) -> tuple[str | None, ...]:
    if value == "all":
        return ("openai", "anthropic")
    return (None if value == "manifest" else value,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Submit the metadata-only run manifest to the hosted assurance "
            "control plane and retrieve its latest decision."
        )
    )
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument(
        "--provider",
        choices=("manifest", "openai", "anthropic", "all"),
        default="manifest",
        help="Use the manifest provider or a synthetic provider-shaped adapter bridge.",
    )
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-non-reauthorized",
        action="store_true",
        help="Return exit code 1 unless every latest decision is reauthorized.",
    )
    args = parser.parse_args(argv)

    try:
        client = HostedControlPlaneClient(
            endpoint=args.endpoint,
            profile=args.profile,
            region=args.region,
        )
        results = [
            build_local_run(
                client,
                args.manifest,
                args.current_revisions,
                provider=provider,
            )
            for provider in _provider_choices(args.provider)
        ]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "status": "blocked",
            "results": [],
            "refusal": {
                "error": "hosted_client_input_invalid",
                "message": "The hosted client could not prepare the request.",
                "guidance": "Repair the manifest, revision map, endpoint, or profile.",
                "source": type(error).__name__,
            },
        }
        print(json.dumps(data, indent=2, sort_keys=True))
        return 1

    data = {
        "client_version": 1,
        "endpoint_host": urlsplit(args.endpoint).hostname,
        "results": results,
    }
    serialised = (
        _markdown(data)
        if args.markdown
        else json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    print(serialised, end="")
    blocked = any("refusal" in result for result in results)
    not_reauthorized = any(
        result.get("latest", {}).get("status") != "reauthorized"
        for result in results
        if isinstance(result.get("latest"), dict)
    )
    return int(blocked or (args.fail_on_non_reauthorized and not_reauthorized))


if __name__ == "__main__":
    raise SystemExit(main())
