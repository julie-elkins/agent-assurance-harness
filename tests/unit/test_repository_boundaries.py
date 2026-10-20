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
