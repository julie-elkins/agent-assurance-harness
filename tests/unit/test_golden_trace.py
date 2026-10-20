from dataclasses import replace
from pathlib import Path

from agent_reliability_lab.golden_trace import (
    compare_golden_trace,
    load_golden_manifest,
    load_replay_for_golden,
)
from agent_reliability_lab.packs import load_builtin_packs
from agent_reliability_lab.replay import HarnessChangeManifest


REPOSITORY = Path(__file__).parents[2]
GOLDEN_REPLAY = REPOSITORY / "examples" / "traces" / "guarded.json"
GOLDEN_MANIFEST = REPOSITORY / "examples" / "traces" / "golden-manifest.json"


def _golden():
    return (
        load_replay_for_golden(GOLDEN_REPLAY),
        load_golden_manifest(GOLDEN_MANIFEST),
    )


def test_golden_trace_matches_guarded_adapter_evidence():
    golden, manifest = _golden()

    report = compare_golden_trace(
        golden,
        replace(
            golden,
            harness_change=HarnessChangeManifest(
                change_id="candidate-golden",
                components=("guardrails",),
            ),
        ),
        manifest=manifest,
        packs=load_builtin_packs(),
    )

    assert report.passed
    assert report.drifts == ()
    assert report.candidate_evaluation_passed is True


def test_golden_trace_catches_evidence_drift_even_when_evaluator_still_passes():
    golden, manifest = _golden()
    case = next(case for case in golden.cases if case.scenario_id == "tool-misuse")
    assert case.response.trace is not None
    original_call = case.response.trace.tool_calls[0]
    changed_trace = replace(
        case.response.trace,
        tool_calls=(replace(original_call, result_id="tool-result-drift"),),
        evidence_ids=("tool-result-drift",),
    )
    changed_case = replace(
        case,
        response=replace(case.response, trace=changed_trace),
    )
    candidate = replace(
        golden,
        cases=tuple(
            changed_case if current.scenario_id == case.scenario_id else current
            for current in golden.cases
        ),
        harness_change=HarnessChangeManifest(
            change_id="candidate-golden-drift",
            components=("tool_guidance",),
        ),
    )

    report = compare_golden_trace(
        golden,
        candidate,
        manifest=manifest,
        packs=load_builtin_packs(),
    )

    assert report.passed is False
    assert report.candidate_evaluation_passed is True
    assert [drift.scenario_id for drift in report.drifts] == ["tool-misuse"]


def test_golden_trace_refuses_stale_manifest():
    golden, manifest = _golden()
    stale = replace(manifest, trace_sha256="0" * 64)

    report = compare_golden_trace(
        golden,
        golden,
        manifest=stale,
        packs=load_builtin_packs(),
    )

    assert report.passed is False
    assert report.refusal is not None
    assert report.refusal.error == "golden_trace_digest_mismatch"
