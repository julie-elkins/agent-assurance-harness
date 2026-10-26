"""Generate metadata-only receipts from the mocked provider adapters."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.evidence_registry import load_evidence_registry
from agent_reliability_lab.change_impact import revisions_digest
from agent_reliability_lab.provider_receipt import (
    RECEIPT_ACCEPTED,
    build_provider_evidence_report,
)
from agent_reliability_lab.providers import mock_provider_adapters
from agent_reliability_lab.protocol import ScenarioRequest
from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.run_manifest import load_current_revisions
from agent_reliability_lab.scenarios import scenarios


def _request_for(scenario_id: str) -> ScenarioRequest:
    scenario = next(
        (item for item in scenarios() if item.scenario_id == scenario_id),
        None,
    )
    if scenario is None:
        raise ValueError(f"unknown synthetic scenario: {scenario_id}")
    return ScenarioRequest(
        scenario_id=scenario.scenario_id,
        task_label=scenario.title,
        available_tools=scenario.available_tools,
        contract=scenario.contract,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run mocked OpenAI- and Anthropic-shaped adapters and emit "
            "metadata-only evidence receipts."
        )
    )
    parser.add_argument("--provider", choices=("openai", "anthropic", "all"), default="all")
    parser.add_argument("--scenario-id", default="tool-misuse")
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--model-openai", default="openai-synthetic")
    parser.add_argument("--model-anthropic", default="anthropic-synthetic")
    parser.add_argument("--harness-revision", default="harness-r1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-refusal", action="store_true")
    args = parser.parse_args(argv)

    try:
        registry = load_evidence_registry(args.registry)
        registration = registry.get(args.evidence_id)
        if registration is None:
            raise ValueError(
                "evidence_id is not registered; add it before emitting a receipt"
            )
        request = _request_for(args.scenario_id)
        revision_values = load_current_revisions(str(args.revisions))
        environment = environment_for_scenario(args.scenario_id)
        adapters = mock_provider_adapters(args.provider)
        runs = tuple(
            (
                adapter.provider_id,
                adapter.run(request, environment),
            )
            for adapter in adapters
        )
        report = build_provider_evidence_report(
            runs,
            evidence_id=args.evidence_id,
            model_ids={
                "openai": args.model_openai,
                "anthropic": args.model_anthropic,
            },
            harness_revision=args.harness_revision,
            revision_digest=revisions_digest(revision_values),
            registration=registration,
        )
        data = report.to_dict()
        serialized = (
            report.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(
            args.fail_on_refusal
            and any(receipt.status != RECEIPT_ACCEPTED for receipt in report.receipts)
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "provider_receipt_version": 1,
            "passed": False,
            "receipts": [],
            "diagnostics": {
                "refusal": "provider_evidence_receipt_input_invalid",
                "source": type(error).__name__,
                "what_it_does_not_show": (
                    "It does not show prompts, provider requests or responses, "
                    "model text, credentials, hidden reasoning, or live provider quality."
                ),
            },
        }
        serialized = (
            "## Provider evidence receipts\n\n"
            "- **Decision:** `BLOCKED`\n"
            "- **Required action:** Repair the registry or synthetic input.\n"
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
