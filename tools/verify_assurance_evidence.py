"""Verify metadata-only assurance evidence against the current checkout."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path

from agent_reliability_lab.pack_provenance import pack_set_sha256
from agent_reliability_lab.packs import load_builtin_packs


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify pull-request assurance reports and attestations against "
            "the current synthetic pack set and Git revision."
        )
    )
    parser.add_argument("--positive-report", type=Path, required=True)
    parser.add_argument("--positive-attestation", type=Path, required=True)
    parser.add_argument("--negative-report", type=Path, required=True)
    parser.add_argument("--negative-attestation", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        positive_report = _read_object(args.positive_report)
        positive_attestation = _read_object(args.positive_attestation)
        negative_report = _read_object(args.negative_report)
        negative_attestation = _read_object(args.negative_attestation)
        _verify_common(
            positive_report,
            positive_attestation,
            expected_passed=True,
        )
        _verify_common(
            negative_report,
            negative_attestation,
            expected_passed=False,
        )
        _verify_positive(positive_attestation)
        _verify_negative(negative_attestation)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {
                    "verified": False,
                    "error": "assurance_evidence_verification_failed",
                    "message": str(error),
                },
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "verified": True,
                "package_version": _package_version(),
                "git_commit": _git_commit(),
                "pack_set_sha256": pack_set_sha256(load_builtin_packs()),
                "positive_blocking_finding_count": positive_attestation[
                    "blocking_finding_count"
                ],
                "negative_blocking_finding_count": negative_attestation[
                    "blocking_finding_count"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def _verify_common(
    report: dict[str, object],
    attestation: dict[str, object],
    *,
    expected_passed: bool,
) -> None:
    if report.get("assurance_attestation") != attestation:
        raise ValueError("Report and standalone attestation do not match.")
    if attestation.get("package") != "agent-reliability-lab":
        raise ValueError("Attestation package is not agent-reliability-lab.")
    if attestation.get("package_version") != _package_version():
        raise ValueError("Attestation package version does not match the checkout.")
    if attestation.get("git_commit") != _git_commit():
        raise ValueError("Attestation Git revision does not match the checkout.")
    if attestation.get("pack_set_sha256") != pack_set_sha256(load_builtin_packs()):
        raise ValueError("Attestation pack-set hash does not match the checkout.")
    if attestation.get("scenario_count") != len(load_builtin_packs()):
        raise ValueError("Attestation scenario count does not match the pack set.")
    if attestation.get("passed") is not expected_passed:
        raise ValueError("Attestation pass state is not the expected control state.")
    if attestation.get("refusal_code") is not None:
        raise ValueError("Control evidence contains an unexpected refusal.")
    manifests = attestation.get("pack_manifests")
    if not isinstance(manifests, list) or len(manifests) != len(load_builtin_packs()):
        raise ValueError("Attestation pack manifests do not cover every pack.")


def _verify_positive(attestation: dict[str, object]) -> None:
    if attestation.get("blocking_finding_count") != 0:
        raise ValueError("Positive control contains a blocking finding.")


def _verify_negative(attestation: dict[str, object]) -> None:
    blocking_count = attestation.get("blocking_finding_count")
    if not isinstance(blocking_count, int) or blocking_count < 1:
        raise ValueError("Negative control did not prove a blocking finding.")


def _package_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
