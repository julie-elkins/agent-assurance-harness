import json

import pytest

from agent_reliability_lab.evidence_registry import load_evidence_registry
from agent_reliability_lab.run_manifest import RunManifestValidationError


def _registry(tmp_path, entry=None):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "evidence_registry_version": 1,
                "entries": [
                    entry
                    or {
                        "evidence_id": "run-001",
                        "decision_target": "release-agent-v1",
                        "dependency_scope": ["policy"],
                        "check_ids": ["policy-regression"],
                        "owner_id": "assurance-team",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_registry_loads_identifier_only_entries(tmp_path):
    registry = load_evidence_registry(_registry(tmp_path))

    assert registry["run-001"].dependency_scope == ("policy",)
    assert registry["run-001"].check_ids == ("policy-regression",)


@pytest.mark.parametrize(
    "entry",
    [
        {
            "evidence_id": "run-001",
            "decision_target": "release-agent-v1",
            "dependency_scope": ["unknown"],
            "check_ids": ["policy-regression"],
            "owner_id": "assurance-team",
        },
        {
            "evidence_id": "run-001",
            "decision_target": "release-agent-v1",
            "dependency_scope": ["policy"],
            "check_ids": ["python tools/run.py"],
            "owner_id": "assurance-team",
        },
    ],
)
def test_registry_rejects_unsafe_entries(tmp_path, entry):
    with pytest.raises(RunManifestValidationError):
        load_evidence_registry(_registry(tmp_path, entry))
