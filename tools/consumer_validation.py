"""Validate the reusable action from a separate synthetic consumer fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agent_reliability_lab.consumer_compatibility import (
    evaluate_consumer_compatibility,
    load_consumer_compatibility_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / "examples" / "consumer-repository"
RUNNER = ROOT / "tools" / "reusable_action_runner.py"
WORKFLOW = CONSUMER / ".github" / "workflows" / "assurance.yml"
ACTION_REF = (
    "5141cf58695a4ed4f45bfbcf106ce559340c61aa"
)
ACTION_USE = (
    "julie-elkins/agent-assurance-harness/.github/actions/agent-assurance@"
    + ACTION_REF
)
APPROVED_MANIFEST = CONSUMER / "policy-manifest.json"
DRIFTED_MANIFEST = CONSUMER / "policy-manifest-drifted.json"
COMPATIBILITY_MANIFEST = CONSUMER / "compatibility-manifest.json"


def _git_commit() -> str:
    """Return the current checkout revision without exporting repository paths."""

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    """Return the exact fingerprint of one checked-in manifest file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workflow_contract() -> dict[str, object]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return {
        "pinned_to_reviewed_commit": text.count(ACTION_USE) == 2,
        "no_moving_action_reference": "@main" not in text,
        "read_only_permissions": "permissions:\n  contents: read" in text,
        "positive_and_negative_jobs": (
            "id: positive" in text
            and "id: negative" in text
            and "continue-on-error: true" in text
        ),
    }


def _run_consumer(
    adapter: str,
    *,
    fail_on_findings: bool,
    manifest_name: str = "policy-manifest.json",
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="agent-assurance-consumer-") as directory:
        output = Path(directory) / "report.json"
        github_output = Path(directory) / "github-output"
        environment = os.environ.copy()
        environment["GITHUB_OUTPUT"] = str(github_output)
        command = [
            sys.executable,
            str(RUNNER),
            "--agent-id",
            "consumer-agent",
            "--adapter-command-json",
            json.dumps([sys.executable, adapter]),
            "--adapter-working-directory",
            str(CONSUMER),
            "--output",
            str(output),
            "--consumer-policy-manifest",
            manifest_name,
            "--mutations",
            "true",
            "--fail-on-findings",
            str(fail_on_findings).lower(),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
        )
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "return_code": completed.returncode,
                "decision": "blocked",
                "passed": False,
                "report_version": None,
                "github_outputs_present": False,
                "consumer_contract_passed": False,
                "consumer_contract_failure_reasons": ["report_unavailable"],
                "policy_manifest_version": None,
            }
        output_text = (
            github_output.read_text(encoding="utf-8")
            if github_output.exists()
            else ""
        )
        return {
            "return_code": completed.returncode,
            "decision": report.get("decision"),
            "passed": report.get("passed"),
            "report_version": report.get("reusable_action_version"),
            "github_outputs_present": (
                "decision=" in output_text and "passed=" in output_text
            ),
            "consumer_contract_passed": (
                isinstance(report.get("consumer_contract"), dict)
                and report["consumer_contract"].get("passed") is True
            ),
            "consumer_contract_failure_reasons": (
                report["consumer_contract"].get("failure_reasons", [])
                if isinstance(report.get("consumer_contract"), dict)
                else ["report_missing_consumer_contract"]
            ),
            "policy_manifest_version": (
                report["consumer_contract"]["manifest"].get("manifest_version")
                if isinstance(report.get("consumer_contract"), dict)
                and isinstance(report["consumer_contract"].get("manifest"), dict)
                else None
            ),
        }


def build_report() -> dict[str, object]:
    workflow = _workflow_contract()
    positive = _run_consumer("guarded_adapter.py", fail_on_findings=True)
    negative = _run_consumer("regressed_adapter.py", fail_on_findings=True)
    policy_drift = _run_consumer(
        "guarded_adapter.py",
        fail_on_findings=True,
        manifest_name="policy-manifest-drifted.json",
    )
    policy_restored = _run_consumer(
        "guarded_adapter.py",
        fail_on_findings=True,
    )
    negative_caught = (
        negative["return_code"] != 0
        and negative["decision"] == "blocked"
        and negative["passed"] is False
    )
    policy_drift_caught = (
        policy_drift["return_code"] != 0
        and policy_drift["decision"] == "blocked"
        and policy_drift["passed"] is False
        and policy_drift["consumer_contract_passed"] is False
        and policy_drift["consumer_contract_failure_reasons"]
        == ["policy_version_mismatch", "policy_digest_mismatch"]
    )
    policy_rollback_restored = (
        policy_restored["return_code"] == 0
        and policy_restored["decision"] == "pass"
        and policy_restored["passed"] is True
        and policy_restored["consumer_contract_passed"] is True
    )
    compatibility_manifest = load_consumer_compatibility_manifest(
        COMPATIBILITY_MANIFEST
    )
    compatibility = evaluate_consumer_compatibility(
        compatibility_manifest,
        action_ref=ACTION_REF,
        consumer_validation_version=3,
        runs={
            "positive": positive,
            "negative": negative,
            "policy-drift": policy_drift,
            "policy-restored": policy_restored,
        },
    )
    policy_replay_provenance = {
        "provenance_version": 1,
        "passed": (
            len(_git_commit()) == 40
            and len(ACTION_REF) == 40
            and _sha256(APPROVED_MANIFEST) != _sha256(DRIFTED_MANIFEST)
            and [
                positive["decision"],
                policy_drift["decision"],
                policy_restored["decision"],
            ]
            == ["pass", "blocked", "pass"]
            and policy_rollback_restored
        ),
        "git_commit": _git_commit(),
        "action_ref": ACTION_REF,
        "manifest_fingerprints": {
            "approved_sha256": _sha256(APPROVED_MANIFEST),
            "drifted_sha256": _sha256(DRIFTED_MANIFEST),
        },
        "state_sequence": [
            {"state": "approved_before", "decision": positive["decision"]},
            {"state": "drifted", "decision": policy_drift["decision"]},
            {"state": "approved_after", "decision": policy_restored["decision"]},
        ],
        "rollback_restored": policy_rollback_restored,
        "diagnostics": {
            "warnings": [
                "The fingerprints identify the checked-in synthetic manifests and "
                "the evaluated checkout; they are not signed provenance.",
            ],
            "what_it_does_not_show": (
                "It does not prove a production deployment rollback, live policy "
                "registry state, or authorization-system restoration."
            ),
        },
    }
    passed = all(workflow.values()) and (
        positive["return_code"] == 0
        and positive["decision"] == "pass"
        and positive["passed"] is True
        and positive["consumer_contract_passed"] is True
        and positive["github_outputs_present"] is True
        and negative_caught
        and negative["consumer_contract_passed"] is False
        and policy_drift_caught
        and policy_rollback_restored
        and policy_replay_provenance["passed"] is True
        and compatibility.passed
    )
    return {
        "consumer_validation_version": 3,
        "consumer_fixture": "synthetic-consumer-repository",
        "action_ref": ACTION_REF,
        "workflow_contract": workflow,
        "positive_run": positive,
        "negative_control": {
            **negative,
            "caught": negative_caught,
        },
        "policy_drift_replay": {
            "approved_before": positive,
            "drifted": {
                **policy_drift,
                "caught": policy_drift_caught,
            },
            "approved_after": {
                **policy_restored,
                "restored": policy_rollback_restored,
            },
            "rollback_restored": policy_rollback_restored,
        },
        "policy_replay_provenance": policy_replay_provenance,
        "compatibility": compatibility.to_dict(),
        "passed": passed,
        "diagnostics": {
            "warnings": [
                "The fixture runs locally through the same bounded subprocess "
                "runner used by the composite action.",
                "The fixture contains synthetic identifiers only.",
            ],
            "what_it_does_not_show": (
                "It does not prove GitHub-hosted runner availability, live provider "
                "quality, or consumer-specific deployment behaviour."
            ),
        },
    }


def _markdown(data: dict[str, object]) -> str:
    positive = data["positive_run"]
    negative = data["negative_control"]
    status = "PASS" if data["passed"] else "BLOCKED"
    return "\n".join(
        [
            "## Reusable action consumer validation",
            "",
            f"- **Decision:** {status}",
            f"- **Action commit:** `{data['action_ref']}`",
            f"- **Positive consumer run:** `{positive['decision']}`",
            f"- **Positive policy contract:** `{positive['consumer_contract_passed']}`",
            f"- **Negative control caught:** `{negative['caught']}`",
            f"- **Negative contract failure reasons:** `{negative['consumer_contract_failure_reasons']}`",
            f"- **Policy drift caught:** `{data['policy_drift_replay']['drifted']['caught']}`",
            f"- **Approved policy restored:** `{data['policy_drift_replay']['rollback_restored']}`",
            f"- **Policy replay provenance:** `{data['policy_replay_provenance']['passed']}`",
            f"- **Compatibility gate:** `{data['compatibility']['passed']}`",
            "",
            "The fixture is synthetic and metadata-only; credentials, prompts, "
            "payloads, and provider output are not exported.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the reusable action from a synthetic consumer fixture."
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)
    data = build_report()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown:
        print(_markdown(data), end="")
    else:
        print(json.dumps(data, indent=2, sort_keys=True))
    return int(args.fail_on_block and not data["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
