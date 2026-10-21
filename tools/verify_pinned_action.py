"""Verify required reusable-action behavior at the consumer's pinned commit.

The tool reads the immutable action object from local Git history and emits only
contract markers, identifiers, and statuses. It never prints the action source.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from agent_reliability_lab.action_parity import verify_action_text
from agent_reliability_lab.consumer_compatibility import (
    load_consumer_compatibility_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT
    / "examples"
    / "consumer-repository"
    / ".github"
    / "workflows"
    / "assurance.yml"
)
COMPATIBILITY_MANIFEST = (
    ROOT / "examples" / "consumer-repository" / "compatibility-manifest.json"
)
ACTION_FILE = ".github/actions/agent-assurance/action.yml"
ACTION_PATTERN = re.compile(r"uses:\s+\S+@([0-9a-f]{40})(?:\s|$)")


def _workflow_action_ref() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    if "@main" in text:
        raise ValueError("moving_action_reference")
    if text.count("consumer-policy-manifest: policy-manifest.json") != 2:
        raise ValueError("consumer_policy_manifest_not_supplied")
    references = ACTION_PATTERN.findall(text)
    if len(references) != 2 or len(set(references)) != 1:
        raise ValueError("inconsistent_action_pin")
    return references[0]


def _read_pinned_action(action_ref: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "show", f"{action_ref}:{ACTION_FILE}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("pinned_action_object_unavailable") from error
    return completed.stdout


def _verify() -> dict[str, object]:
    action_ref = _workflow_action_ref()
    compatibility = load_consumer_compatibility_manifest(COMPATIBILITY_MANIFEST)
    if compatibility.required_action_ref != action_ref:
        raise ValueError("compatibility_manifest_action_pin_mismatch")
    parity = verify_action_text(_read_pinned_action(action_ref))
    result = parity.to_dict()
    result["action_ref"] = action_ref
    result["compatibility_manifest_action_ref"] = compatibility.required_action_ref
    result["verified"] = parity.passed
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify required action behavior at the pinned commit."
    )
    parser.add_argument("--fail-on-unverified", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = _verify()
    except (OSError, ValueError, json.JSONDecodeError):
        result = {
            "action_parity_version": 1,
            "verified": False,
            "error": "pinned_action_parity_verification_failed",
        }
    print(json.dumps(result, sort_keys=True))
    return int(args.fail_on_unverified and result.get("verified") is not True)


if __name__ == "__main__":
    raise SystemExit(main())
