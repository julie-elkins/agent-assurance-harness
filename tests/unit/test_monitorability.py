from pathlib import Path

from agent_reliability_lab.monitorability import (
    MONITORABILITY_REVIEW,
    MONITORABILITY_READY,
    build_monitorability_report,
    force_monitor_miss,
    load_monitorability_fixture,
)
from agent_reliability_lab.run_manifest import (
    load_current_revisions,
    load_manifest,
)
from agent_reliability_lab.safety_case import (
    SAFETY_CASE_READY,
    build_safety_case,
)


ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "examples" / "monitorability" / "cases.json"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"
CHANGED = ROOT / "examples" / "change-impact" / "current-revisions.json"


def _report(revisions_path: Path):
    return build_monitorability_report(
        load_monitorability_fixture(FIXTURE),
        load_manifest(str(MANIFEST)),
        load_current_revisions(str(revisions_path)),
    )


def test_reference_fixture_measures_monitor_and_evaluator_separately():
    report = _report(CURRENT)

    assert report.status == MONITORABILITY_READY
    assert report.monitor_metrics.recall.rate == 1.0
    assert report.monitor_metrics.false_positive_rate.rate == 0.0
    assert report.evaluator_metrics.accuracy.rate == 1.0
    assert report.monitor_evaluation_awareness.absolute_gap == 0.0
    assert report.split_metrics["held_out"].recall.rate == 1.0
    assert report.split_metrics["benign"].false_positive_rate.rate == 0.0


def test_negative_control_reports_held_out_monitor_miss():
    fixture = force_monitor_miss(load_monitorability_fixture(FIXTURE))
    report = build_monitorability_report(
        fixture,
        load_manifest(str(MANIFEST)),
        load_current_revisions(str(CURRENT)),
    )

    assert report.status == MONITORABILITY_REVIEW
    assert "held_out_monitor_recall_below_threshold" in report.reasons
    assert report.split_metrics["held_out"].recall.rate == 0.5


def test_changed_revision_requires_reauthorization():
    report = _report(CHANGED)

    assert report.status == MONITORABILITY_REVIEW
    assert "reauthorization:reauthorization_required" in report.reasons
    assert report.reauthorization.status == "reauthorization_required"


def test_safety_case_preserves_human_review_boundary():
    case = build_safety_case(
        _report(CURRENT),
        decision_target="release-agent-v1",
    )

    assert case.status == SAFETY_CASE_READY
    assert case.required_human_review is True
    assert case.to_dict()["monitorability_report"]["status"] == MONITORABILITY_READY
    assert "not a signed attestation" in case.to_markdown()
