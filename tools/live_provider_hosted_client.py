"""Run bounded local provider trials and submit metadata to the hosted service.

This command is deliberately local-only. It reads a provider credential from the fixed
environment variable required by ``live.py``, never prints provider responses, and sends
only the validated run manifest and aggregated trial metadata to AWS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_reliability_lab.hosted_client import HostedControlPlaneClient
from agent_reliability_lab.live import LiveProviderPolicy
from agent_reliability_lab.live_hosted import (
    DEFAULT_TRIALS,
    run_live_trials,
    submit_live_run,
)
from agent_reliability_lab.providers import ProviderLimits


_CREDENTIAL_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _refusal(error: str, message: str, guidance: str) -> dict[str, object]:
    return {
        "error": error,
        "message": message,
        "guidance": guidance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run repeated, bounded local OpenAI or Anthropic synthetic trials "
            "and submit only their metadata to the hosted assurance service."
        )
    )
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--provider", choices=("openai", "anthropic"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicitly permit the bounded local provider calls.",
    )
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--max-elapsed-seconds", type=float, required=True)
    parser.add_argument("--max-estimated-cost-usd", type=float, required=True)
    parser.add_argument("--estimated-cost-usd-per-request", type=float, required=True)
    args = parser.parse_args(argv)

    credential_env_var = _CREDENTIAL_ENV[args.provider]
    policy = LiveProviderPolicy(
        provider_id=args.provider,
        model=args.model,
        credential_env_var=credential_env_var,
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=args.max_output_tokens,
            max_elapsed_seconds=args.max_elapsed_seconds,
            max_estimated_cost_usd=args.max_estimated_cost_usd,
        ),
        estimated_cost_usd_per_request=args.estimated_cost_usd_per_request,
        allow_network=args.allow_network,
    )

    try:
        live_run = run_live_trials(
            args.manifest,
            args.current_revisions,
            provider=args.provider,
            model=args.model,
            model_revision=args.model_revision,
            scenario_id=args.scenario_id,
            policy=policy,
            trials=args.trials,
        )
        if live_run.payload is None:
            data = {
                "provider": args.provider,
                "model": args.model,
                "model_revision": args.model_revision,
                "scenario_id": args.scenario_id,
                "trial_count": len(live_run.trials),
                "successful_trial_count": live_run.successful_trials,
                "refusal": live_run.refusal
                or _refusal(
                    "live_provider_evidence_missing",
                    "The provider trials did not produce a safe hosted payload.",
                    "Repair the bounded local trial before retrying.",
                ),
            }
            print(json.dumps(data, indent=2, sort_keys=True))
            return 1

        client = HostedControlPlaneClient(
            endpoint=args.endpoint,
            profile=args.profile,
            region=args.region,
        )
        data = submit_live_run(client, live_run)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "provider": args.provider,
            "model": args.model,
            "model_revision": args.model_revision,
            "scenario_id": args.scenario_id,
            "refusal": _refusal(
                "live_provider_input_invalid",
                "The live provider bridge could not prepare the run.",
                f"Repair the local inputs; failure type: {type(error).__name__}.",
            ),
        }
        print(json.dumps(data, indent=2, sort_keys=True))
        return 1

    data["metadata_only"] = True
    data["credential_env_var"] = credential_env_var
    data["credential_value_observed"] = bool(os.environ.get(credential_env_var))
    print(json.dumps(data, indent=2, sort_keys=True))
    latest = data.get("latest")
    return int(
        "refusal" in data
        or not isinstance(latest, dict)
        or latest.get("status") != "reauthorized"
    )


if __name__ == "__main__":
    raise SystemExit(main())
