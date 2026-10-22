"""Check public-repository security and delivery boundaries.

This is intentionally a small, dependency-free check. It catches high-signal
credential material and verifies that the blocking GitHub Actions workflow cannot
silently become a live-provider workflow.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "reliability.yml"
PUBLIC_ACTION = ROOT / ".github" / "actions" / "agent-assurance" / "action.yml"
GITHUB_ROOT = ROOT / ".github"

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:sk-(?:proj|live|ant)?-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)
EXTERNAL_ACTION_PATTERN = re.compile(
    r"^\s*uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s#]+)"
)
FULL_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials",
    "credentials.json",
}
FORBIDDEN_SECRET_SUFFIXES = {".pem", ".p12", ".pfx"}
LIVE_WORKFLOW_MARKERS = (
    "--allow-network",
    "--live-provider",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "secrets.",
    "write-all",
)
PUBLIC_ACTION_MARKERS = (
    "--allow-network",
    "--live-provider",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "secrets.",
    "id-token: write",
    "attestations: write",
)
PUSH_PROVENANCE_JOB = "\n  release-provenance:\n"


def main() -> int:
    failures = []
    tracked_paths = _tracked_paths()
    for relative_path in tracked_paths:
        path = ROOT / relative_path
        if _is_forbidden_secret_path(relative_path):
            failures.append(f"credential-like file is tracked: {relative_path}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(
                    f"high-signal credential pattern found in: {relative_path}"
                )
                break

    failures.extend(_workflow_failures())
    failures.extend(_public_action_failures())
    failures.extend(_unpinned_action_failures())
    if failures:
        print("Repository boundary check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        f"Repository boundary check passed for {len(tracked_paths)} tracked files."
    )
    return 0


def _tracked_paths() -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return tuple(
        Path(item)
        for item in result.stdout.decode("utf-8").split("\0")
        if item
    )


def _is_forbidden_secret_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in FORBIDDEN_SECRET_FILENAMES
        or name.endswith(tuple(FORBIDDEN_SECRET_SUFFIXES))
    )


def _workflow_failures() -> list[str]:
    try:
        workflow = WORKFLOW.read_text(encoding="utf-8")
    except OSError as error:
        return [f"required workflow could not be read: {error}"]

    failures = []
    for marker in LIVE_WORKFLOW_MARKERS:
        if marker in workflow:
            failures.append(
                f"blocking workflow contains forbidden live or elevated marker: {marker}"
            )
    failures.extend(_provenance_permission_failures(workflow))
    if "permissions:" not in workflow or "contents: read" not in workflow:
        failures.append("blocking workflow must declare permissions: contents: read")
    return failures


def _provenance_permission_failures(workflow: str) -> list[str]:
    """Allow signing permissions only in the explicitly trusted push job."""

    main_workflow, separator, trusted_jobs = workflow.partition(
        PUSH_PROVENANCE_JOB
    )
    elevated_markers = ("id-token: write", "attestations: write")
    failures = [
        (
            "blocking workflow grants release-signing permissions outside "
            "the release-provenance job"
        )
        for marker in elevated_markers
        if marker in main_workflow
    ]

    if not separator:
        if any(marker in workflow for marker in elevated_markers):
            failures.append(
                "blocking workflow has release-signing permissions but no "
                "release-provenance job"
            )
        return failures

    provenance_job, promotion_separator, promotion_job = trusted_jobs.partition(
        "\n  release-promotion:\n"
    )
    required_controls = (
        "if: (github.event_name == 'push' && github.ref == 'refs/heads/main') || (github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' && inputs.release_approval == 'approve')",
        "needs: reliability",
        "permissions:",
        "contents: read",
        "id-token: write",
        "attestations: write",
    )
    for control in required_controls:
        if control not in provenance_job:
            failures.append(
                f"release-provenance job is missing required control: {control}"
            )
    if not promotion_separator:
        failures.append("workflow is missing the release-promotion job")
    else:
        promotion_controls = (
            "if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' && inputs.release_approval == 'approve'",
            "needs: release-provenance",
            "environment:",
            "name: release",
            "permissions:",
            "contents: read",
            "attestations: read",
            "tools/provenance_report.py",
        )
        for control in promotion_controls:
            if control not in promotion_job:
                failures.append(
                    f"release-promotion job is missing required control: {control}"
                )
    return failures


def _public_action_failures() -> list[str]:
    try:
        action = PUBLIC_ACTION.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as error:
        return [f"public action could not be read: {error}"]

    return [
        f"public action contains forbidden live or credential marker: {marker}"
        for marker in PUBLIC_ACTION_MARKERS
        if marker in action
    ]


def _unpinned_action_failures() -> list[str]:
    """Require immutable commit references for every external GitHub Action."""

    failures = []
    for path in sorted(GITHUB_ROOT.rglob("*")):
        if path.suffix not in {".yml", ".yaml"} or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        relative_path = path.relative_to(GITHUB_ROOT.parent)
        for line_number, line in enumerate(lines, start=1):
            match = EXTERNAL_ACTION_PATTERN.match(line)
            if match is None:
                continue
            reference = match.group(2)
            if not FULL_COMMIT_SHA_PATTERN.fullmatch(reference):
                failures.append(
                    "external GitHub Action must use a full commit SHA: "
                    f"{relative_path}:{line_number}"
                )
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
