import json
from pathlib import Path

from agent_reliability_lab.change_impact import (
    IMPACT_READY,
    IMPACT_RERUN_REQUIRED,
    build_change_impact_plan,
)
from agent_reliability_lab.evidence_registry import load_evidence_registry
from agent_reliability_lab.rerun_executor import (
    RERUN_BLOCKED,
    RERUN_COMPLETED,
    RERUN_NOT_REQUIRED,
    RERUN_REFUSED,
    RerunPolicy,
    run_bounded_rerun,
    supported_check_ids,
)
from agent_reliability_lab.run_manifest import (
    REQUIRED_REVISION_KEYS,
    RunManifest,
)


ROOT = Path(__file__).parents[2]


def _revisions(**overrides):
    values = {key: f"{key}-r1" for key in REQUIRED_REVISION_KEYS}
    values.update(overrides)
    return values


def _manifest() -> RunManifest:
    data = json.loads(
        (ROOT / "examples" / "run-manifest" / "manifest.json").read_text()
    )
    return RunManifest.from_dict(data)


def _registry():
    return load_evidence_registry(
        ROOT / "examples" / "change-impact" / "evidence-registry.json"
    )


def _plan(**kwargs):
    return build_change_impact_plan(
        [_manifest()],
        _revisions(),
        _revisions(**kwargs),
        registry=_registry(),
    )


def test_unchanged_plan_does_not_run_suite():
    called = False

    def suite_runner():
        nonlocal called
        called = True
        raise AssertionError("unchanged evidence must not run checks")

    plan = _plan()
    execution = run_bounded_rerun(plan, suite_runner=suite_runner)

    assert plan.status == IMPACT_READY
    assert execution.status == RERUN_NOT_REQUIRED
    assert called is False


def test_changed_plan_runs_allowlisted_checks_and_catches_controls():
    execution = run_bounded_rerun(_plan(policy="policy-r2"))

    assert execution.status == RERUN_COMPLETED
    assert execution.selected_check_ids == (
        "authorization-negative-controls",
        "evidence-completeness-gate",
        "tool-safety-regression",
    )
    assert all(result.status == "completed" for result in execution.results)
    assert all(result.negative_control_caught for result in execution.results)


def test_unknown_check_id_is_refused_before_suite_runs():
    plan = _plan(policy="policy-r2")
    original = plan.evidence[0]
    from dataclasses import replace

    changed = replace(
        plan,
        evidence=(
            replace(original, rerun_checks=("not-allowlisted",)),
        ),
        status=IMPACT_RERUN_REQUIRED,
    )
    called = False

    def suite_runner():
        nonlocal called
        called = True
        raise AssertionError("unknown checks must not dispatch")

    execution = run_bounded_rerun(changed, suite_runner=suite_runner)

    assert execution.status == RERUN_REFUSED
    assert execution.reason_codes == ("unknown_check_id",)
    assert called is False


def test_max_check_limit_blocks_before_suite_runs():
    called = False

    def suite_runner():
        nonlocal called
        called = True
        raise AssertionError("limit should block before dispatch")

    execution = run_bounded_rerun(
        _plan(policy="policy-r2"),
        policy=RerunPolicy(max_checks=2),
        suite_runner=suite_runner,
    )

    assert execution.status == RERUN_BLOCKED
    assert execution.reason_codes == ("max_checks_exceeded",)
    assert called is False


def test_supported_ids_are_code_side_and_stable():
    assert supported_check_ids() == (
        "abstention-negative-controls",
        "authorization-negative-controls",
        "evaluator-validity-negative-controls",
        "evidence-completeness-gate",
        "tool-safety-regression",
    )
