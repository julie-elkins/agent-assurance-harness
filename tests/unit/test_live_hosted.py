from pathlib import Path

from agent_reliability_lab.hosted_client import HostedResponse
from agent_reliability_lab.live import LiveProviderPolicy
from agent_reliability_lab.live_hosted import (
    LiveTrial,
    build_live_submission_payload,
    run_live_trials,
    submit_live_run,
)
from agent_reliability_lab.providers import ProviderLimits
from agent_reliability_lab.run_manifest import load_current_revisions, load_manifest


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "examples/run-manifest/manifest.json"
CURRENT = ROOT / "examples/run-manifest/current-revisions.json"


def _policy(provider: str = "openai") -> LiveProviderPolicy:
    return LiveProviderPolicy(
        provider_id=provider,
        model="synthetic-live-model",
        credential_env_var=(
            "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        ),
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=64,
            max_elapsed_seconds=5.0,
            max_estimated_cost_usd=0.05,
        ),
        estimated_cost_usd_per_request=0.01,
        allow_network=True,
    )


def _trials(*passed: bool) -> tuple[LiveTrial, ...]:
    return tuple(
        LiveTrial(
            passed=value,
            requests=1,
            output_tokens=12,
            elapsed_seconds=0.5,
            estimated_cost_usd=0.01,
        )
        for value in passed
    )


def test_live_payload_records_repeatability_and_actual_model_revision():
    manifest = load_manifest(str(MANIFEST))
    current = load_current_revisions(str(CURRENT))

    payload = build_live_submission_payload(
        manifest,
        current,
        provider="openai",
        model="gpt-synthetic-live",
        model_revision="gpt-synthetic-live-r1",
        scenario_id="tool-misuse",
        policy=_policy(),
        trials=_trials(True, True),
    )
    result = payload["manifest"]

    assert result["provider"] == "openai"
    assert result["model"] == "gpt-synthetic-live"
    assert result["revisions"]["model"] == "gpt-synthetic-live-r1"
    assert payload["current_revisions"]["model"] == "gpt-synthetic-live-r1"
    assert result["repeatability"]["run_count"] == 2
    assert result["repeatability"]["successful_run_count"] == 2
    assert result["budget"]["observed"]["requests"] == 2
    assert "within_limits" not in result["budget"]
    assert "provider_output" not in result


def test_live_trials_use_injected_trial_runner_without_network():
    calls = []

    def trial_runner(number: int) -> LiveTrial:
        calls.append(number)
        return LiveTrial(True, 1, 10, 0.25, 0.01)

    result = run_live_trials(
        MANIFEST,
        CURRENT,
        provider="anthropic",
        model="claude-synthetic-live",
        model_revision="claude-synthetic-live-r1",
        scenario_id="false-completion",
        policy=_policy("anthropic"),
        trials=2,
        trial_runner=trial_runner,
    )

    assert result.refusal is None
    assert result.passed is True
    assert calls == [1, 2]
    assert result.payload["manifest"]["repeatability"]["run_count"] == 2


def test_failed_trial_is_recorded_as_failed_outcome_not_success():
    result = run_live_trials(
        MANIFEST,
        CURRENT,
        provider="openai",
        model="gpt-synthetic-live",
        model_revision="gpt-synthetic-live-r1",
        scenario_id="inappropriate-answer",
        policy=_policy(),
        trials=2,
        trial_runner=lambda number: LiveTrial(
            passed=number == 1,
            requests=1,
            output_tokens=10,
            elapsed_seconds=0.25,
            estimated_cost_usd=0.01,
        ),
    )

    assert result.passed is False
    assert result.payload["manifest"]["evidence"]["observed_outcome"] == "failed"
    assert result.payload["manifest"]["repeatability"]["successful_run_count"] == 1


def test_network_opt_in_is_required_before_live_trials():
    policy = _policy()
    policy = LiveProviderPolicy(
        provider_id=policy.provider_id,
        model=policy.model,
        credential_env_var=policy.credential_env_var,
        limits=policy.limits,
        estimated_cost_usd_per_request=policy.estimated_cost_usd_per_request,
        allow_network=False,
    )

    result = run_live_trials(
        MANIFEST,
        CURRENT,
        provider="openai",
        model="gpt-synthetic-live",
        model_revision="gpt-synthetic-live-r1",
        scenario_id="tool-misuse",
        policy=policy,
        trials=2,
    )

    assert result.payload is None
    assert result.refusal["error"] == "network_opt_in_required"


def test_submit_live_run_returns_only_bounded_hosted_fields():
    class FakeClient:
        def submit(self, payload):
            return HostedResponse(
                200,
                {
                    "run_id": "run-live",
                    "audit_id": "audit-live",
                    "status": "reauthorized",
                    "supports_decision": True,
                },
            )

        def get_latest(self, run_id):
            return HostedResponse(
                200,
                {
                    "run_id": run_id,
                    "status": "reauthorized",
                    "supports_decision": True,
                    "submitted_by": "arn:aws:sts::private",
                },
            )

    live_run = run_live_trials(
        MANIFEST,
        CURRENT,
        provider="openai",
        model="gpt-synthetic-live",
        model_revision="gpt-synthetic-live-r1",
        scenario_id="tool-misuse",
        policy=_policy(),
        trials=2,
        trial_runner=lambda number: LiveTrial(True, 1, 10, 0.25, 0.01),
    )

    result = submit_live_run(FakeClient(), live_run)

    assert result["latest"] == {
        "run_id": "run-live",
        "status": "reauthorized",
        "supports_decision": True,
    }
    assert "submitted_by" not in str(result)
