import json
from pathlib import Path

import pytest

from agent_reliability_lab.source_evidence import (
    SourceEvidenceReceipt,
    load_source_evidence_receipt,
)
from agent_reliability_lab.run_manifest import RunManifestValidationError


ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "source-evidence" / "receipt.json"


def test_example_receipt_is_strictly_loadable():
    receipt = load_source_evidence_receipt(EXAMPLE)

    assert receipt.human_disposition == "pending_review"
    assert receipt.support_status == "insufficient"
    assert "claim_text" not in receipt.to_dict()
    assert "source_body" not in receipt.to_dict()


def test_incomplete_lookup_cannot_claim_support():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["lookup_status"] = "unavailable"
    data["support_status"] = "supports"

    with pytest.raises(RunManifestValidationError, match="not_evaluated"):
        SourceEvidenceReceipt.from_dict(data)


def test_receipt_rejects_raw_claim_text():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["claim_text"] = "private item wording"

    with pytest.raises(RunManifestValidationError, match="unsupported keys"):
        SourceEvidenceReceipt.from_dict(data)


def test_receipt_rejects_unbounded_scope():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["scope"]["free_form"] = "anything"

    with pytest.raises(RunManifestValidationError, match="bounded metadata"):
        SourceEvidenceReceipt.from_dict(data)
