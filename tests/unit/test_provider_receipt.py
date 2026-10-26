import json
from pathlib import Path

from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.change_impact import revisions_digest
from agent_reliability_lab.evidence_registry import load_evidence_registry
from agent_reliability_lab.provider_receipt import (
    RECEIPT_ACCEPTED,
    RECEIPT_REFUSED,
    build_provider_evidence_receipt,
    build_provider_evidence_report,
)
from agent_reliability_lab.providers import (
    ProviderLimits,
    mock_provider_adapters,
)
from agent_reliability_lab.protocol import ScenarioRequest
from agent_reliability_lab.scenarios import scenarios


ROOT = Path(__file__).parents[2]
REGISTRY = load_evidence_registry(
    ROOT / "examples" / "change-impact" / "evidence-registry.json"
)
REGISTRATION = REGISTRY["run-synthetic-001"]
REVISION_DIGEST = revisions_digest(
    json.loads(
        (ROOT / "examples" / "change-impact" / "baseline-revisions.json").read_text()
    )
)


def _request():
    scenario = next(item for item in scenarios() if item.scenario_id == "tool-misuse")
    return ScenarioRequest(
        scenario_id=scenario.scenario_id,
        task_label=scenario.title,
        available_tools=scenario.available_tools,
        contract=scenario.contract,
    )


def test_both_providers_produce_the_same_receipt_contract():
    request = _request()
    environment = environment_for_scenario(request.scenario_id)
    adapters = mock_provider_adapters("all")
    runs = tuple(
        (adapter.provider_id, adapter.run(request, environment))
        for adapter in adapters
    )

    report = build_provider_evidence_report(
        runs,
        evidence_id="run-synthetic-001",
        model_ids={
            "openai": "openai-synthetic",
            "anthropic": "anthropic-synthetic",
        },
        harness_revision="harness-r1",
        revision_digest=REVISION_DIGEST,
        registration=REGISTRATION,
    )

    assert report.passed is True
    assert {receipt.provider_id for receipt in report.receipts} == {
        "openai",
        "anthropic",
    }
    assert all(receipt.status == RECEIPT_ACCEPTED for receipt in report.receipts)
    assert all(
        receipt.rerun_check_ids == REGISTRATION.check_ids
        for receipt in report.receipts
    )


def test_receipt_is_metadata_only():
    request = _request()
    adapter = mock_provider_adapters("openai")[0]
    run = adapter.run(request, environment_for_scenario(request.scenario_id))
    serialized = json.dumps(
        build_provider_evidence_receipt(
            run,
            evidence_id="run-synthetic-001",
            provider_id="openai",
            model_id="openai-synthetic",
            harness_revision="harness-r1",
            revision_digest=REVISION_DIGEST,
            registration=REGISTRATION,
        ).to_dict()
    )

    assert '"text":' not in serialized
    assert "The requested policy was checked." not in serialized
    assert "synthetic raw provider text" not in serialized
    assert "tool-result-001" not in serialized


def test_unknown_evidence_id_is_refused_before_provider_receipt():
    request = _request()
    adapter = mock_provider_adapters("openai")[0]
    run = adapter.run(request, environment_for_scenario(request.scenario_id))

    try:
        build_provider_evidence_receipt(
            run,
            evidence_id="unregistered-evidence",
            provider_id="openai",
            model_id="openai-synthetic",
            harness_revision="harness-r1",
            revision_digest=REVISION_DIGEST,
            registration=REGISTRATION,
        )
    except ValueError as error:
        assert "match evidence_id" in str(error)
    else:
        raise AssertionError("unregistered evidence must be refused")


def test_provider_refusal_becomes_bounded_refusal_receipt():
    request = _request()
    adapter = mock_provider_adapters(
        "openai",
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=1,
            max_elapsed_seconds=5.0,
            max_estimated_cost_usd=0.01,
        ),
    )[0]
    run = adapter.run(request, environment_for_scenario(request.scenario_id))
    receipt = build_provider_evidence_receipt(
        run,
        evidence_id="run-synthetic-001",
        provider_id="openai",
        model_id="openai-synthetic",
        harness_revision="harness-r1",
        revision_digest=REVISION_DIGEST,
        registration=REGISTRATION,
    )

    assert receipt.status == RECEIPT_REFUSED
    assert receipt.refusal_code == "provider_token_limit_exceeded"
    assert receipt.event_count == 0
