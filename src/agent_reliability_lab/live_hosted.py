"""Bridge bounded local provider runs into the hosted metadata-only control plane.

Design rules:

1. Reuse ``live.py`` for the only provider network call; this module orchestrates it
   but does not create a second endpoint, retry policy, or credential path.
2. Run at least two bounded trials so a single lucky model response cannot be reported
   as repeatable evidence.
3. Build the hosted request from the validated run-manifest model and aggregate only
   usage, status, identifiers, and digests; provider responses are discarded.
4. Keep network opt-in, provider model identity, revision identity, and spend ceilings
   explicit at the command boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .hosted_client import (
    HostedControlPlaneClient,
    HostedResponse,
    decision_view,
    safe_submission_payload,
)
from .live import HttpTransport, LiveProviderPolicy, live_provider_adapter
from .providers import ProviderLimits
from .run_manifest import RunManifest, load_current_revisions, load_manifest
from .runner import run_adapter_scenario


# MODELLING ASSUMPTION: two trials are the minimum useful repeatability demonstration;
# three is the local ceiling until a separate sampling decision exists.
DEFAULT_TRIALS = 2
MAX_TRIALS = 3
_PROVIDER_IDS = frozenset({"openai", "anthropic"})
_IDENTIFIER = re.compile(r"^[^\s]{1,128}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


@dataclass(frozen=True)
class LiveTrial:
    """Identifier-only usage and outcome metadata from one provider trial."""

    passed: bool
    requests: int
    output_tokens: int
    elapsed_seconds: float
    estimated_cost_usd: float


@dataclass(frozen=True)
class LiveRun:
    """The safe result of repeated local provider execution."""

    provider: str
    model: str
    model_revision: str
    scenario_id: str
    trials: tuple[LiveTrial, ...]
    payload: dict[str, object] | None
    refusal: dict[str, object] | None

    @property
    def successful_trials(self) -> int:
        """Return the number of trials whose shared checks passed."""

        return sum(trial.passed for trial in self.trials)

    @property
    def passed(self) -> bool:
        """Return whether every recorded trial passed."""

        return bool(self.trials) and self.successful_trials == len(self.trials)


def _refusal(error: str, message: str, guidance: str) -> dict[str, object]:
    return {
        "error": error,
        "message": message,
        "guidance": guidance,
    }


def _validate_identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field} must be a non-empty identifier without whitespace.")


def _trial_from_report(
    scenario_id: str,
    policy: LiveProviderPolicy,
    *,
    transport: HttpTransport | None,
) -> LiveTrial:
    report = run_adapter_scenario(
        live_provider_adapter(policy, transport=transport),
        scenario_id,
    )
    agent_report = report.reports[0]
    budget = agent_report.execution_budgets.get(scenario_id)
    if budget is None:
        return LiveTrial(False, 0, 0, 0.0, 0.0)
    return LiveTrial(
        passed=agent_report.passed,
        requests=budget.requests,
        output_tokens=budget.output_tokens,
        elapsed_seconds=budget.elapsed_seconds,
        estimated_cost_usd=budget.estimated_cost_usd,
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_live_submission_payload(
    manifest: RunManifest,
    current_revisions: Mapping[str, str],
    *,
    provider: str,
    model: str,
    model_revision: str,
    scenario_id: str,
    policy: LiveProviderPolicy,
    trials: tuple[LiveTrial, ...],
) -> dict[str, object]:
    """Create one metadata-only hosted payload from repeated trial summaries."""

    if provider not in _PROVIDER_IDS:
        raise ValueError("provider must be openai or anthropic.")
    _validate_identifier(model, "model")
    _validate_identifier(model_revision, "model_revision")
    _validate_identifier(scenario_id, "scenario_id")
    if not trials:
        raise ValueError("trials must not be empty.")
    run_suffix = hashlib.sha256(
        f"{provider}:{model_revision}".encode("utf-8")
    ).hexdigest()[:10]
    run_id = f"{manifest.run_id}-{provider}-{scenario_id}-{run_suffix}"
    decision_target = f"{manifest.decision_target}-{scenario_id}"
    if not _RUN_ID.fullmatch(run_id) or len(run_id) > 128:
        raise ValueError("the generated live run identifier is too long or unsafe.")

    request_count = sum(trial.requests for trial in trials)
    output_tokens = sum(trial.output_tokens for trial in trials)
    elapsed_seconds = sum(trial.elapsed_seconds for trial in trials)
    estimated_cost_usd = sum(trial.estimated_cost_usd for trial in trials)
    successful_trials = sum(trial.passed for trial in trials)
    success_rate = successful_trials / len(trials)
    # MODELLING ASSUMPTION: Bernoulli variance is the honest metadata-only variance
    # available when the evaluator records only pass/fail trial outcomes.
    variance = success_rate * (1.0 - success_rate)
    now = datetime.now(timezone.utc).isoformat()

    data = manifest.to_dict()
    data.update(
        {
            "run_id": run_id,
            "decision_target": decision_target,
            "provider": provider,
            "model": model,
            "agent_id": f"{provider}-live",
            "created_at": now,
            "checkpoint": {
                "checkpoint_id": None,
                "checkpoint_revision": None,
                "resume_supported": False,
            },
            "repeatability": {
                "run_count": len(trials),
                "successful_run_count": successful_trials,
                "variance": {"task_success_rate": variance},
            },
            "evidence": {
                "scope": [scenario_id],
                "digest": _digest(
                    {
                        "provider": provider,
                        "model": model,
                        "model_revision": model_revision,
                        "scenario_id": scenario_id,
                        "trials": [
                            {
                                "passed": trial.passed,
                                "requests": trial.requests,
                                "output_tokens": trial.output_tokens,
                            }
                            for trial in trials
                        ],
                    }
                ),
                "expires_at": manifest.evidence_expires_at,
                "observed_outcome": (
                    "success" if successful_trials == len(trials) else "failed"
                ),
            },
            "budget": {
                "observed": {
                    "requests": request_count,
                    "output_tokens": output_tokens,
                    "elapsed_seconds": elapsed_seconds,
                    "estimated_cost_usd": estimated_cost_usd,
                },
                "limits": {
                    "max_requests": policy.limits.max_requests * len(trials),
                    "max_output_tokens": (
                        policy.limits.max_output_tokens * len(trials)
                    ),
                    "max_elapsed_seconds": (
                        policy.limits.max_elapsed_seconds * len(trials)
                    ),
                    "max_estimated_cost_usd": (
                        policy.limits.max_estimated_cost_usd * len(trials)
                    ),
                },
                "stop_condition": (
                    f"stop after {len(trials)} trials; one provider request per "
                    f"trial and {policy.limits.max_elapsed_seconds} seconds per trial"
                ),
            },
        }
    )
    revisions = data["revisions"]
    assert isinstance(revisions, dict)
    revisions["model"] = model_revision
    current = dict(current_revisions)
    current["model"] = model_revision
    return safe_submission_payload(
        RunManifest.from_dict(data),
        current,
    )


def run_live_trials(
    manifest_path: Path,
    current_revisions_path: Path,
    *,
    provider: str,
    model: str,
    model_revision: str,
    scenario_id: str,
    policy: LiveProviderPolicy,
    trials: int = DEFAULT_TRIALS,
    transport: HttpTransport | None = None,
    trial_runner: Callable[[int], LiveTrial] | None = None,
) -> LiveRun:
    """Run repeated bounded provider trials and prepare one hosted payload."""

    if provider not in _PROVIDER_IDS:
        raise ValueError("provider must be openai or anthropic.")
    if trials < 2 or trials > MAX_TRIALS:
        raise ValueError(f"trials must be between 2 and {MAX_TRIALS}.")
    _validate_identifier(model, "model")
    _validate_identifier(model_revision, "model_revision")
    _validate_identifier(scenario_id, "scenario_id")
    refusal = policy.validate()
    if refusal is not None:
        return LiveRun(
            provider,
            model,
            model_revision,
            scenario_id,
            (),
            None,
            refusal.to_dict(),
        )
    manifest = load_manifest(str(manifest_path))
    current_revisions = load_current_revisions(str(current_revisions_path))
    runner = trial_runner
    if runner is None:
        runner = lambda _trial_number: _trial_from_report(
            scenario_id,
            policy,
            transport=transport,
        )
    results = tuple(runner(number) for number in range(1, trials + 1))
    if any(trial.requests == 0 for trial in results):
        return LiveRun(
            provider,
            model,
            model_revision,
            scenario_id,
            results,
            None,
            _refusal(
                "live_provider_evidence_missing",
                "At least one provider trial did not produce bounded usage evidence.",
                "Repair the provider response or credentials before submitting hosted evidence.",
            ),
        )
    payload = build_live_submission_payload(
        manifest,
        current_revisions,
        provider=provider,
        model=model,
        model_revision=model_revision,
        scenario_id=scenario_id,
        policy=policy,
        trials=results,
    )
    return LiveRun(
        provider,
        model,
        model_revision,
        scenario_id,
        results,
        payload,
        None,
    )


def submit_live_run(
    client: HostedControlPlaneClient,
    live_run: LiveRun,
) -> dict[str, object]:
    """Submit one safe live-run payload and retrieve its bounded decision."""

    result: dict[str, object] = {
        "provider": live_run.provider,
        "model": live_run.model,
        "model_revision": live_run.model_revision,
        "scenario_id": live_run.scenario_id,
        "trial_count": len(live_run.trials),
        "successful_trial_count": live_run.successful_trials,
    }
    if live_run.refusal is not None:
        result["refusal"] = live_run.refusal
        return result
    assert live_run.payload is not None
    submission = client.submit(live_run.payload)
    if submission.refusal is not None:
        result["refusal"] = submission.refusal
        return result
    if submission.body is None:
        result["refusal"] = _refusal(
            "hosted_response_missing",
            "The hosted service returned no decision body.",
            "Inspect the hosted service status before retrying.",
        )
        return result
    hosted_refusal = submission.body.get("refusal")
    if isinstance(hosted_refusal, dict):
        result["refusal"] = hosted_refusal
        return result
    result["submission"] = decision_view(submission.body)
    run_id = submission.body.get("run_id")
    if not isinstance(run_id, str):
        result["refusal"] = _refusal(
            "hosted_response_incomplete",
            "The hosted service response did not include a run identifier.",
            "Inspect the hosted service contract before retrying.",
        )
        return result
    latest = client.get_latest(run_id)
    if latest.refusal is not None:
        result["refusal"] = latest.refusal
    elif latest.body is None:
        result["refusal"] = _refusal(
            "hosted_response_missing",
            "The hosted service returned no latest decision body.",
            "Inspect the hosted service status before retrying.",
        )
    elif isinstance(latest.body.get("refusal"), dict):
        result["refusal"] = latest.body["refusal"]
    else:
        result["latest"] = decision_view(latest.body)
    return result


__all__ = [
    "DEFAULT_TRIALS",
    "LiveRun",
    "LiveTrial",
    "MAX_TRIALS",
    "build_live_submission_payload",
    "run_live_trials",
    "submit_live_run",
]
