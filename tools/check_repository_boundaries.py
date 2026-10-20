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

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:sk-(?:proj|live|ant)?-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)
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
    "id-token: write",
)


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
    if "permissions:" not in workflow or "contents: read" not in workflow:
        failures.append("blocking workflow must declare permissions: contents: read")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
