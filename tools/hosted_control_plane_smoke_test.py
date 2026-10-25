"""Run the hosted control-plane contract without contacting AWS.

The smoke test follows four rules:

1. Exercise the Lambda HTTP boundary rather than bypassing it.
2. Use only the checked-in synthetic manifest and revision fixtures.
3. Prove both approval and refusal directions, including unauthorised access.
4. Emit check names and states, never request bodies or provider content.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab import control_plane_handler
from agent_reliability_lab.control_plane import InMemoryAuditStore


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT_REVISIONS_PATH = (
    ROOT / "examples" / "run-manifest" / "current-revisions.json"
)
CHANGED_REVISIONS_PATH = (
    ROOT / "examples" / "run-manifest" / "changed-revisions.json"
)
FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {"prompt", "tool_arguments", "provider_output", "credentials"}
)


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _payload(revisions_path: Path) -> dict[str, object]:
    return {
        "manifest": _load(MANIFEST_PATH),
        "current_revisions": _load(revisions_path),
    }


def _principal_context() -> dict[str, object]:
    return {
        "requestContext": {
            "identity": {
                "userArn": "arn:aws:iam::123456789012:user/synthetic-smoke-test"
            }
        }
    }


def _post(payload: dict[str, object]) -> dict[str, object]:
    event = {
        **_principal_context(),
        "httpMethod": "POST",
        "resource": "/reauthorizations",
        "body": json.dumps(payload, sort_keys=True),
    }
    return control_plane_handler.lambda_handler(event, None)


def _get(run_id: str) -> dict[str, object]:
    event = {
        **_principal_context(),
        "httpMethod": "GET",
        "resource": "/runs/{run_id}",
        "pathParameters": {"run_id": run_id},
    }
    return control_plane_handler.lambda_handler(event, None)


def _body(response: dict[str, object]) -> dict[str, object]:
    value = response.get("body")
    if not isinstance(value, str):
        raise ValueError("response body was not JSON text")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("response body was not an object")
    return parsed


def _check(
    checks: list[dict[str, object]],
    name: str,
    passed: bool,
) -> None:
    checks.append({"name": name, "status": "passed" if passed else "failed"})
    if not passed:
        raise ValueError(f"smoke check failed: {name}")


def run() -> dict[str, object]:
    """Return a metadata-only synthetic smoke-test report."""

    checks: list[dict[str, object]] = []
    control_plane_handler._STORE = InMemoryAuditStore()
    unauthorised = control_plane_handler.lambda_handler(
        {
            "httpMethod": "POST",
            "resource": "/reauthorizations",
            "body": "{}",
        },
        None,
    )
    _check(
        checks,
        "unauthorised_request_rejected",
        unauthorised["statusCode"] == 401,
    )

    current = _body(_post(_payload(CURRENT_REVISIONS_PATH)))
    _check(
        checks,
        "current_evidence_reauthorized",
        current["status"] == "reauthorized"
        and current["supports_decision"] is True,
    )

    changed = _body(_post(_payload(CHANGED_REVISIONS_PATH)))
    _check(
        checks,
        "changed_revisions_require_reauthorization",
        changed["status"] == "reauthorization_required"
        and changed["supports_decision"] is False,
    )

    run_id = "run-synthetic-001"
    latest = _body(_get(run_id))
    _check(
        checks,
        "audit_record_retrievable",
        latest["run_id"] == run_id
        and latest["status"] == "reauthorization_required",
    )
    _check(
        checks,
        "audit_record_contains_no_content_fields",
        not FORBIDDEN_OUTPUT_FIELDS.intersection(latest),
    )
    _check(
        checks,
        "audit_record_has_expiry",
        isinstance(latest.get("expires_at_epoch"), int)
        and latest["expires_at_epoch"] > 0,
    )
    return {
        "status": "passed",
        "checks": checks,
        "data_class": "synthetic_metadata_only",
        "live_aws_contacted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the hosted control-plane synthetic smoke test."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run()
        exit_code = 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report = {
            "status": "blocked",
            "checks": [],
            "data_class": "synthetic_metadata_only",
            "live_aws_contacted": False,
            "refusal": {
                "error": "smoke_test_refused",
                "message": "The hosted control-plane smoke test did not complete.",
                "guidance": "Repair the local boundary before selecting an AWS environment.",
                "source": type(error).__name__,
            },
        }
        exit_code = 1
    serialised = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised, encoding="utf-8")
    print(serialised, end="")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
