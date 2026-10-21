"""Independently verify consumer policy replay evidence against the checkout.

Design rules:

1. The verifier recomputes checkout identity and manifest fingerprints; it does not
   trust the report's embedded provenance values.
2. The consumer workflow supplies the action revision, so a moving or inconsistent pin
   is refused before report evidence is accepted.
3. The approved, drifted, and restored states must appear in order with the expected
   decisions and restoration result.
4. Output contains identifiers, hashes, and states only; report paths and adapter
   payloads never enter the result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT
    / "examples"
    / "consumer-repository"
    / ".github"
    / "workflows"
    / "assurance.yml"
)
DEFAULT_APPROVED_MANIFEST = (
    ROOT / "examples" / "consumer-repository" / "policy-manifest.json"
)
DEFAULT_DRIFTED_MANIFEST = (
    ROOT / "examples" / "consumer-repository" / "policy-manifest-drifted.json"
)
_ACTION_PATTERN = re.compile(r"uses:\s+\S+@([0-9a-f]{40})(?:\s|$)")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_STATES = (
    {"state": "approved_before", "decision": "pass"},
    {"state": "drifted", "decision": "blocked"},
    {"state": "approved_after", "decision": "pass"},
)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object.")
    return value


def _read_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, "consumer validation report")


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workflow_action_ref() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    if "@main" in text:
        raise ValueError("Consumer workflow uses a moving action reference.")
    if text.count("consumer-policy-manifest: policy-manifest.json") != 2:
        raise ValueError("Consumer workflow does not pass the approved policy manifest.")
    references = _ACTION_PATTERN.findall(text)
    if len(references) != 2 or len(set(references)) != 1:
        raise ValueError("Consumer workflow does not use one consistent action pin.")
    return references[0]


def _verify(
    report: dict[str, Any],
    *,
    approved_manifest: Path,
    drifted_manifest: Path,
) -> dict[str, object]:
    current_commit = _git_commit()
    action_ref = _workflow_action_ref()
    approved_sha256 = _sha256(approved_manifest)
    drifted_sha256 = _sha256(drifted_manifest)

    if report.get("consumer_validation_version") != 2:
        raise ValueError("Consumer validation report version is not supported.")
    if report.get("passed") is not True:
        raise ValueError("Consumer validation did not pass.")
    provenance = _object(
        report.get("policy_replay_provenance"),
        "policy_replay_provenance",
    )
    if provenance.get("passed") is not True:
        raise ValueError("Policy replay provenance did not pass.")
    if provenance.get("git_commit") != current_commit:
        raise ValueError("Replay report Git revision does not match the checkout.")
    if report.get("action_ref") != action_ref:
        raise ValueError("Replay report action revision does not match the workflow.")
    if provenance.get("action_ref") != action_ref:
        raise ValueError("Replay provenance action revision does not match the workflow.")

    fingerprints = _object(
        provenance.get("manifest_fingerprints"),
        "manifest_fingerprints",
    )
    if fingerprints.get("approved_sha256") != approved_sha256:
        raise ValueError("Approved policy manifest fingerprint does not match.")
    if fingerprints.get("drifted_sha256") != drifted_sha256:
        raise ValueError("Drifted policy manifest fingerprint does not match.")
    if approved_sha256 == drifted_sha256:
        raise ValueError("Approved and drifted policy manifests are identical.")
    if not _HASH_PATTERN.fullmatch(approved_sha256) or not _HASH_PATTERN.fullmatch(
        drifted_sha256
    ):
        raise ValueError("Policy manifest fingerprint is not a SHA-256 value.")

    state_sequence = provenance.get("state_sequence")
    if state_sequence != list(EXPECTED_STATES):
        raise ValueError("Policy replay state sequence is incomplete or out of order.")
    replay = _object(report.get("policy_drift_replay"), "policy_drift_replay")
    if replay.get("rollback_restored") is not True:
        raise ValueError("Policy replay did not prove restoration.")
    if provenance.get("rollback_restored") is not True:
        raise ValueError("Replay provenance did not prove restoration.")

    if not _COMMIT_PATTERN.fullmatch(current_commit):
        raise ValueError("Current Git revision is not a commit identifier.")
    return {
        "verified": True,
        "consumer_validation_version": 2,
        "git_commit": current_commit,
        "action_ref": action_ref,
        "manifest_fingerprints": {
            "approved_sha256": approved_sha256,
            "drifted_sha256": drifted_sha256,
        },
        "state_sequence": list(EXPECTED_STATES),
        "rollback_restored": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify consumer policy replay provenance."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--approved-manifest",
        type=Path,
        default=DEFAULT_APPROVED_MANIFEST,
    )
    parser.add_argument(
        "--drifted-manifest",
        type=Path,
        default=DEFAULT_DRIFTED_MANIFEST,
    )
    parser.add_argument("--fail-on-unverified", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = _verify(
            _read_report(args.report),
            approved_manifest=args.approved_manifest,
            drifted_manifest=args.drifted_manifest,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        result = {
            "verified": False,
            "error": "consumer_provenance_verification_failed",
            "message": str(error),
        }
    print(json.dumps(result, sort_keys=True))
    return int(args.fail_on_unverified and result.get("verified") is not True)


if __name__ == "__main__":
    raise SystemExit(main())
