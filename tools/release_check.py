"""Verify that the built release artifact matches the tested source behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_ARGS = (
    "--mock-provider",
    "all",
    "--json",
    "--mutations",
    "--fail-on-findings",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and verify a clean install of the release artifact."
    )
    parser.add_argument(
        "--sbom-output",
        type=Path,
        help="Optional path for the runtime CycloneDX JSON SBOM.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        help="Optional path for the metadata-only release manifest.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = _run_release_check(
            sbom_output=args.sbom_output,
        )
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Release check failed: {error}", file=sys.stderr)
        return 1

    serialized = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.manifest_output is not None:
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


def _run_release_check(*, sbom_output: Path | None) -> dict[str, object]:
    package_version = _package_version()
    git_commit, working_tree_dirty = _git_state()
    with tempfile.TemporaryDirectory(prefix="agent-reliability-release-") as directory:
        workspace = Path(directory)
        distribution_directory = workspace / "dist"
        _run(
            [
                "uv",
                "build",
                "--out-dir",
                str(distribution_directory),
            ]
        )
        wheel = _only_file(distribution_directory, "*.whl")
        source_distribution = _only_file(distribution_directory, "*.tar.gz")

        runtime_requirements = workspace / "runtime-requirements.txt"
        exported = _run(
            [
                "uv",
                "export",
                "--format",
                "requirements-txt",
                "--no-emit-project",
                "--no-dev",
            ]
        )
        runtime_requirements.write_text(exported.stdout, encoding="utf-8")

        temporary_sbom = workspace / "runtime-sbom.json"
        sbom_path = sbom_output or temporary_sbom
        sbom_path.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--disable-pip",
                "--require-hashes",
                "--format",
                "cyclonedx-json",
                "--output",
                str(sbom_path),
                "--requirement",
                str(runtime_requirements),
            ]
        )

        environment_directory = workspace / "environment"
        _run(["uv", "venv", "--python", "3.11", str(environment_directory)])
        python = _venv_python(environment_directory)
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "--requirement",
                str(runtime_requirements),
            ]
        )
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                str(wheel),
            ]
        )

        clean_environment = _clean_environment()
        source_report = _json_command(
            ["uv", "run", "--frozen", "agent-reliability", *CHECK_ARGS],
            cwd=ROOT,
            environment=clean_environment,
        )
        artifact_command = str(
            environment_directory / ("Scripts" if os.name == "nt" else "bin")
            / "agent-reliability"
        )
        artifact_report = _json_command(
            [artifact_command, *CHECK_ARGS],
            cwd=workspace,
            environment=clean_environment,
        )
        if source_report != artifact_report:
            raise ValueError(
                "the installed artifact produced different synthetic assurance output"
            )

        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
        return {
            "manifest_version": 1,
            "package": "agent-reliability-lab",
            "package_version": package_version,
            "git_commit": git_commit,
            "working_tree_dirty": working_tree_dirty,
            "checks": [
                "source_and_artifact_synthetic_cli_match",
                "runtime_dependency_sbom_generated",
            ],
            "artifacts": {
                "wheel_sha256": _sha256(wheel),
                "source_distribution_sha256": _sha256(source_distribution),
            },
            "scenario_pack_sha256": {
                path.name: _sha256(path)
                for path in sorted(
                    (ROOT / "src" / "agent_reliability_lab" / "scenario_packs").glob(
                        "*.json"
                    )
                )
            },
            "assurance_output_sha256": _json_sha256(source_report),
            "sbom_sha256": _sha256(sbom_path),
            "sbom_component_count": len(sbom.get("components", [])),
            "sbom_persisted": sbom_output is not None,
        }


def _package_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def _git_state() -> tuple[str, bool]:
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    status = _run(["git", "status", "--porcelain"]).stdout
    return commit, bool(status)


def _only_file(directory: Path, pattern: str) -> Path:
    matches = tuple(directory.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {pattern} in {directory}")
    return matches[0]


def _venv_python(directory: Path) -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    path = directory / relative
    if not path.exists():
        raise ValueError(f"virtual environment Python was not created: {path}")
    return path


def _clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("ANTHROPIC_API_KEY", None)
    return environment


def _json_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> dict[str, object]:
    result = _run(command, cwd=cwd, environment=environment)
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("assurance command did not return a JSON object")
    return parsed


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


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
