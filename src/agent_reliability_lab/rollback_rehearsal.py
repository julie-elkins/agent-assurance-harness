"""Metadata-only rehearsal of restoring a last-known-good release artifact.

The rehearsal is deliberately local and disposable. It archives the current Git
revision, extracts that artifact into temporary directories, injects a synthetic
failure into one copy, and restores a clean copy from the archive. It never
changes the checkout, calls a deployment system, or uses the network.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


ROLLBACK_REHEARSAL_VERSION = 1
_FAILURE_MARKER = ".synthetic-release-failure"


def _identifier(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(
            not (character.isalnum() or character in "._:/-")
            for character in value
        )
    ):
        raise ValueError(f"{field} must be a non-empty identifier.")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer.")
    return value


@dataclass(frozen=True)
class RollbackPlan:
    """Validated, public, synthetic rollback-rehearsal policy."""

    rollback_plan_version: int
    rollback_id: str
    method: str
    target: str
    failure_injection: str
    verification: str
    max_elapsed_seconds: int
    external_writes_allowed: bool
    network_allowed: bool


@dataclass(frozen=True)
class RollbackRehearsalReport:
    """Metadata-only result of one rollback rehearsal."""

    passed: bool
    git_commit: str
    package_version: str
    failure_injection_applied: bool
    failure_injection_detected: bool
    original_tree_sha256: str
    failed_tree_sha256: str
    restored_tree_sha256: str
    restored_match: bool
    elapsed_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "rollback_rehearsal_version": ROLLBACK_REHEARSAL_VERSION,
            "passed": self.passed,
            "git_commit": self.git_commit,
            "package_version": self.package_version,
            "failure_injection": {
                "type": "synthetic-release-marker",
                "applied": self.failure_injection_applied,
                "detected": self.failure_injection_detected,
            },
            "recovery": {
                "method": "git-archive-restore-rehearsal",
                "target": "last-known-good-commit",
                "original_tree_sha256": self.original_tree_sha256,
                "failed_tree_sha256": self.failed_tree_sha256,
                "restored_tree_sha256": self.restored_tree_sha256,
                "restored_match": self.restored_match,
            },
            "side_effects": {
                "external_writes_attempted": False,
                "network_used": False,
            },
            "verification": {
                "check": "restored-artifact-integrity",
                "passed": self.passed,
            },
            "elapsed_seconds": self.elapsed_seconds,
            "diagnostics": {
                "warnings": [
                    "This is a disposable local artifact rehearsal; it does "
                    "not perform or prove a production deployment rollback.",
                    "The tree digests identify artifact state but are not "
                    "signed provenance statements.",
                ],
                "what_it_does_not_show": (
                    "It does not show deployment health, external state, "
                    "provider output, prompts, credentials, or raw files."
                ),
            },
        }

    def to_markdown(self) -> str:
        status = "PASS" if self.passed else "BLOCKED"
        return "\n".join(
            [
                "# Rollback rehearsal",
                "",
                f"- **Decision:** {status}",
                f"- **Git revision:** `{self.git_commit}`",
                f"- **Package version:** `{self.package_version}`",
                "- **Method:** `git-archive-restore-rehearsal`",
                "- **External writes:** none",
                "- **Network:** disabled",
                "",
                "## Recovery evidence",
                "",
                "| Check | Result |",
                "| --- | --- |",
                f"| Synthetic failure injected | "
                f"{'PASS' if self.failure_injection_applied else 'BLOCKED'} |",
                f"| Synthetic failure detected | "
                f"{'PASS' if self.failure_injection_detected else 'BLOCKED'} |",
                f"| Restored artifact matches baseline | "
                f"{'PASS' if self.restored_match else 'BLOCKED'} |",
                f"| Verification | {'PASS' if self.passed else 'BLOCKED'} |",
                "",
                "The rehearsal uses temporary directories and does not modify "
                "the checkout or a deployment target.",
                "",
            ]
        )


def load_rollback_plan(path: Path) -> RollbackPlan:
    """Load and strictly validate the public rollback plan."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Rollback plan must be an object.")
    allowed = {
        "rollback_plan_version",
        "rollback_id",
        "method",
        "target",
        "failure_injection",
        "verification",
        "max_elapsed_seconds",
        "external_writes_allowed",
        "network_allowed",
    }
    if set(data) - allowed:
        raise ValueError("Rollback plan contains unknown fields.")
    if data.get("rollback_plan_version") != ROLLBACK_REHEARSAL_VERSION:
        raise ValueError("rollback_plan_version is not supported.")
    if data.get("external_writes_allowed") is not False:
        raise ValueError("external_writes_allowed must be false.")
    if data.get("network_allowed") is not False:
        raise ValueError("network_allowed must be false.")
    return RollbackPlan(
        rollback_plan_version=ROLLBACK_REHEARSAL_VERSION,
        rollback_id=_identifier(data.get("rollback_id"), "rollback_id"),
        method=_identifier(data.get("method"), "method"),
        target=_identifier(data.get("target"), "target"),
        failure_injection=_identifier(
            data.get("failure_injection"), "failure_injection"
        ),
        verification=_identifier(data.get("verification"), "verification"),
        max_elapsed_seconds=_positive_int(
            data.get("max_elapsed_seconds"),
            "max_elapsed_seconds",
        ),
        external_writes_allowed=False,
        network_allowed=False,
    )


def run_rollback_rehearsal(
    plan_path: Path,
    repository_root: Path,
) -> RollbackRehearsalReport:
    """Run the disposable rollback rehearsal described by ``plan_path``."""

    plan = load_rollback_plan(plan_path)
    if plan.method != "git-archive-restore-rehearsal":
        raise ValueError("Rollback plan method is not supported.")
    if plan.target != "last-known-good-commit":
        raise ValueError("Rollback plan target is not supported.")
    if plan.failure_injection != "synthetic-release-marker":
        raise ValueError("Rollback failure injection is not supported.")
    if plan.verification != "restored-artifact-integrity":
        raise ValueError("Rollback verification is not supported.")

    started = time.monotonic()
    git_commit = _git_commit(repository_root)
    package_version = _package_version(repository_root)
    archive = _git_archive(repository_root)
    with tempfile.TemporaryDirectory(prefix="agent-assurance-") as temporary_path:
        temporary = Path(temporary_path)
        original = temporary / "original"
        failed = temporary / "failed"
        restored = temporary / "restored"
        _extract_archive(archive, original)
        shutil.copytree(original, failed)
        marker = failed / _FAILURE_MARKER
        marker.write_text("synthetic release failure\n", encoding="utf-8")
        _extract_archive(archive, restored)

        original_digest = _tree_sha256(original)
        failed_digest = _tree_sha256(failed)
        restored_digest = _tree_sha256(restored)
        failure_applied = marker.is_file()
        failure_detected = failure_applied and failed_digest != original_digest
        restored_match = restored_digest == original_digest

    elapsed = time.monotonic() - started
    passed = (
        failure_applied
        and failure_detected
        and restored_match
        and elapsed <= plan.max_elapsed_seconds
    )
    return RollbackRehearsalReport(
        passed=passed,
        git_commit=git_commit,
        package_version=package_version,
        failure_injection_applied=failure_applied,
        failure_injection_detected=failure_detected,
        original_tree_sha256=original_digest,
        failed_tree_sha256=failed_digest,
        restored_tree_sha256=restored_digest,
        restored_match=restored_match,
        elapsed_seconds=round(elapsed, 6),
    )


def _git_commit(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("Current Git revision is not a commit identifier.")
    return value


def _package_version(repository_root: Path) -> str:
    with (repository_root / "pyproject.toml").open("rb") as stream:
        value = tomllib.load(stream)["project"]["version"]
    return _identifier(value, "package version")


def _git_archive(repository_root: Path) -> bytes:
    result = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _extract_archive(archive: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
        members = stream.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
            ):
                raise ValueError("Git archive contains an unsafe member.")
        stream.extractall(destination, members=members)


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
