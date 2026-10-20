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


def test_public_action_has_no_live_or_credential_markers():
    assert _CHECKER._public_action_failures() == []
