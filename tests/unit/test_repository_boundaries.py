import importlib.util
from pathlib import Path


_CHECKER_PATH = (
    Path(__file__).resolve().parents[2] / "tools" / "check_repository_boundaries.py"
)
_SPEC = importlib.util.spec_from_file_location("repository_boundary_checker", _CHECKER_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_CHECKER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CHECKER)

_provenance_permission_failures = _CHECKER._provenance_permission_failures
_unpinned_action_failures = _CHECKER._unpinned_action_failures


def test_push_only_provenance_permissions_are_allowed():
    workflow = """
jobs:
  reliability:
    permissions:
      contents: read
  release-provenance:
    if: (github.event_name == 'push' && github.ref == 'refs/heads/main') || (github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' && inputs.release_approval == 'approve')
    needs: reliability
    permissions:
      contents: read
      id-token: write
      attestations: write
  release-promotion:
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' && inputs.release_approval == 'approve'
    needs: release-provenance
    environment:
      name: release
    permissions:
      contents: read
      attestations: read
    steps:
      - name: Re-verify signed release provenance
        run: uv run python tools/provenance_report.py
"""

    assert _provenance_permission_failures(workflow) == []


def test_provenance_permissions_outside_trusted_job_are_blocked():
    workflow = """
permissions:
  id-token: write
jobs:
  reliability:
    permissions:
      contents: read
"""

    failures = _provenance_permission_failures(workflow)

    assert failures
    assert "outside the release-provenance job" in failures[0]


def test_external_action_refs_must_be_immutable_commits(monkeypatch, tmp_path):
    github_root = tmp_path / ".github" / "workflows"
    github_root.mkdir(parents=True)
    workflow = github_root / "test.yml"
    workflow.write_text(
        """
steps:
  - name: Check out
    uses: actions/checkout@v4
  - name: Upload
    uses: actions/upload-artifact@0123456789abcdef0123456789abcdef01234567
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(_CHECKER, "GITHUB_ROOT", tmp_path / ".github")
    failures = _unpinned_action_failures()

    assert len(failures) == 1
    assert ".github/workflows/test.yml:4" in failures[0]
