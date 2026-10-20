"""Generate the public metadata-only synthetic benchmark report."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

from agent_reliability_lab.benchmark import run_synthetic_benchmark


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a metadata-only synthetic assurance benchmark."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON benchmark report.",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero if a guarded benchmark path regresses.",
    )
    args = parser.parse_args(argv)

    benchmark = run_synthetic_benchmark()
    report = {
        "report_version": 1,
        "package": "agent-reliability-lab",
        "package_version": _package_version(),
        "git_commit": _git_commit(),
        "working_tree_dirty": bool(_run(["git", "status", "--porcelain"])),
        "scenario_pack_sha256": _scenario_pack_hashes(),
        "benchmark": benchmark.to_dict(),
        "benchmark_sha256": _json_sha256(benchmark.to_dict()),
    }
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    if args.fail_on_findings and not benchmark.gate_passed:
        return 1
    return 0


def _package_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def _git_commit() -> str:
    return _run(["git", "rev-parse", "HEAD"]).strip()


def _scenario_pack_hashes() -> dict[str, str]:
    return {
        path.name: _sha256(path)
        for path in sorted(
            (ROOT / "src" / "agent_reliability_lab" / "scenario_packs").glob(
                "*.json"
            )
        )
    }


def _run(command: list[str]) -> str:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
