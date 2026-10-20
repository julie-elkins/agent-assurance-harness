"""Audit the locked third-party dependency set without auditing this editable project."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    exported = subprocess.run(
        [
            "uv",
            "export",
            "--format",
            "requirements-txt",
            "--no-emit-project",
            "--extra",
            "dev",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    with tempfile.TemporaryDirectory(prefix="agent-reliability-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        requirements.write_text(exported.stdout, encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--disable-pip",
                "--require-hashes",
                "--requirement",
                str(requirements),
            ],
            cwd=ROOT,
            check=False,
        )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
