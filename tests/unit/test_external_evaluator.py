import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent_reliability_lab.external_evaluator import (
    EXTERNAL_IMPORT_BLOCKED,
    EXTERNAL_IMPORT_REVIEW,
    import_external_evaluator_result,
    load_external_evaluator_result,
)
from agent_reliability_lab.run_manifest import (
    load_current_revisions,
    load_manifest,
)


ROOT = Path(__file__).parents[2]
INSPECT = ROOT / "examples" / "external-evaluator" / "inspect-result.json"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"
CHANGED = ROOT / "examples" / "change-impact" / "current-revisions.json"


def test_external_result_reuses_canonical_monitorability_contract():
    result = load_external_evaluator_result(INSPECT)
    report = import_external_evaluator_result(
        result,
        load_manifest(str(MANIFEST)),
        load_current_revisions(str(CURRENT)),
    )

    assert report.import_status == "accepted"
    assert report.monitorability_report is not None
    assert report.monitorability_report.status == "ready_for_human_review"
    assert report.safety_case is not None


def test_changed_revision_requires_review_without_rewriting_source_result():
    result = load_external_evaluator_result(INSPECT)
    report = import_external_evaluator_result(
        result,
        load_manifest(str(MANIFEST)),
        load_current_revisions(str(CHANGED)),
    )

    assert report.import_status == EXTERNAL_IMPORT_REVIEW
    assert report.reasons == ("reauthorization:reauthorization_required",)
    assert report.monitorability_report is not None


def test_mismatched_external_revision_is_blocked_before_scoring():
    result = load_external_evaluator_result(INSPECT)
    mismatched = replace(
        result,
        revision_digest="sha256:" + ("c" * 64),
    )
    report = import_external_evaluator_result(
        mismatched,
        load_manifest(str(MANIFEST)),
        load_current_revisions(str(CURRENT)),
    )

    assert report.import_status == EXTERNAL_IMPORT_BLOCKED
    assert report.reasons == ("external_evaluator_revision_mismatch",)
    assert report.monitorability_report is None


def test_content_bearing_field_is_refused(tmp_path):
    value = json.loads(INSPECT.read_text(encoding="utf-8"))
    value["transcript"] = "must not be accepted"
    path = tmp_path / "external-result.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported fields"):
        load_external_evaluator_result(path)
