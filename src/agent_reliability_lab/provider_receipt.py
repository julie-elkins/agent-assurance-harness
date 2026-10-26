"""Metadata-only provider evidence receipts.

Receipts bind a translated provider-shaped run to a registered evidence result.
They deliberately summarize an adapter boundary instead of exporting its trace.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .evidence_registry import EvidenceRegistration
from .protocol import AdapterRun, validate_adapter_run


PROVIDER_RECEIPT_VERSION = 1
RECEIPT_ACCEPTED = "accepted"
RECEIPT_REFUSED = "refused"
RECEIPT_BLOCKED = "blocked"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_PROVIDERS = frozenset({"openai", "anthropic"})


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty identifier")
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field} contains unsupported characters")
    return value


def _optional_identifier(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field)


def _digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _registry_digest(registration: EvidenceRegistration) -> str:
    return _digest(registration.to_dict())


@dataclass(frozen=True)
class ProviderEvidenceReceipt:
    """A portable summary of one provider adapter result."""

    receipt_id: str
    evidence_id: str
    decision_target: str
    provider_id: str
    model_id: str
    agent_id: str
    scenario_id: str
    harness_revision: str
    status: str
    registry_entry_digest: str
    dependency_scope: tuple[str, ...]
    rerun_check_ids: tuple[str, ...]
    owner_id: str
    event_count: int
    event_type_counts: dict[str, int]
    tool_call_count: int
    evidence_id_count: int
    transport_status: str | None
    semantic_outcome: str | None
    usage: dict[str, object] | None
    refusal_code: str | None
    receipt_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_receipt_version": PROVIDER_RECEIPT_VERSION,
            "receipt_id": self.receipt_id,
            "evidence_id": self.evidence_id,
            "decision_target": self.decision_target,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "agent_id": self.agent_id,
            "scenario_id": self.scenario_id,
            "harness_revision": self.harness_revision,
            "status": self.status,
            "registry_entry_digest": self.registry_entry_digest,
            "dependency_scope": list(self.dependency_scope),
            "rerun_check_ids": list(self.rerun_check_ids),
            "owner_id": self.owner_id,
            "event_count": self.event_count,
            "event_type_counts": dict(sorted(self.event_type_counts.items())),
            "tool_call_count": self.tool_call_count,
            "evidence_id_count": self.evidence_id_count,
            "transport_status": self.transport_status,
            "semantic_outcome": self.semantic_outcome,
            "usage": self.usage,
            "refusal_code": self.refusal_code,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True)
class ProviderEvidenceReceiptReport:
    """A bounded collection of provider receipts."""

    receipts: tuple[ProviderEvidenceReceipt, ...]

    @property
    def passed(self) -> bool:
        return bool(self.receipts) and all(
            receipt.status == RECEIPT_ACCEPTED for receipt in self.receipts
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_receipt_version": PROVIDER_RECEIPT_VERSION,
            "passed": self.passed,
            "receipts": [receipt.to_dict() for receipt in self.receipts],
            "diagnostics": {
                "network": "disabled",
                "data_boundary": "metadata_only",
                "what_it_does_not_show": (
                    "It does not show prompts, provider requests or responses, "
                    "model text, credentials, hidden reasoning, or live provider quality."
                ),
            },
        }

    def to_markdown(self) -> str:
        lines = [
            "# Provider evidence receipts",
            "",
            f"- **Decision:** {'PASS' if self.passed else 'BLOCKED'}",
            "- **Network:** disabled; mocked adapters only",
            "- **Content boundary:** metadata only",
            "",
            "| Provider | Evidence | Status | Checks | Owner |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| `{receipt.provider_id}` | `{receipt.evidence_id}` | "
            f"`{receipt.status}` | "
            f"{', '.join(receipt.rerun_check_ids)} | `{receipt.owner_id}` |"
            for receipt in self.receipts
        )
        lines.extend(
            [
                "",
                "The receipt contains identifiers, counts, statuses, digests, and "
                "bounded usage metadata only.",
                "",
            ]
        )
        return "\n".join(lines)


def build_provider_evidence_receipt(
    run: AdapterRun,
    *,
    evidence_id: str,
    provider_id: str,
    model_id: str,
    harness_revision: str,
    registration: EvidenceRegistration,
) -> ProviderEvidenceReceipt:
    """Build one receipt without exporting trace content."""

    provider_id = _identifier(provider_id, "provider_id")
    if provider_id not in _PROVIDERS:
        raise ValueError("provider_id must be openai or anthropic")
    evidence_id = _identifier(evidence_id, "evidence_id")
    model_id = _identifier(model_id, "model_id")
    harness_revision = _identifier(harness_revision, "harness_revision")
    if registration.evidence_id != evidence_id:
        raise ValueError("registration evidence_id must match evidence_id")
    if registration.decision_target == "":
        raise ValueError("registration decision_target must not be empty")

    protocol_refusal = validate_adapter_run(run)
    status = RECEIPT_ACCEPTED
    refusal_code: str | None = None
    event_count = len(run.events)
    event_type_counts: dict[str, int] = {}
    tool_call_count = 0
    evidence_id_count = 0
    transport_status: str | None = None
    semantic_outcome: str | None = None
    usage = run.execution_budget.to_dict() if run.execution_budget else None
    agent_id = "unknown-agent"
    scenario_id = "unknown-scenario"

    if protocol_refusal is not None:
        status = RECEIPT_BLOCKED
        refusal_code = _identifier(protocol_refusal.error, "refusal_code")
    elif run.refusal is not None:
        status = RECEIPT_REFUSED
        refusal_code = _identifier(run.refusal.error, "refusal_code")
    else:
        assert run.trace is not None
        agent_id = _identifier(run.trace.agent_id, "agent_id")
        scenario_id = _identifier(run.trace.scenario_id, "scenario_id")
        transport_status = _optional_identifier(
            run.trace.transport_status, "transport_status"
        )
        semantic_outcome = _optional_identifier(
            run.trace.semantic_outcome, "semantic_outcome"
        )
        tool_call_count = len(run.trace.tool_calls)
        evidence_id_count = len(run.trace.evidence_ids)
        for event in run.events:
            event_type = event.event_type.value
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

    receipt_body = {
        "evidence_id": evidence_id,
        "provider_id": provider_id,
        "model_id": model_id,
        "agent_id": agent_id,
        "scenario_id": scenario_id,
        "harness_revision": harness_revision,
        "status": status,
        "registry_entry_digest": _registry_digest(registration),
        "event_count": event_count,
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "tool_call_count": tool_call_count,
        "evidence_id_count": evidence_id_count,
        "transport_status": transport_status,
        "semantic_outcome": semantic_outcome,
        "usage": usage,
        "refusal_code": refusal_code,
    }
    receipt_digest = _digest(receipt_body)
    receipt_id = "receipt:" + receipt_digest.removeprefix("sha256:")[:24]
    return ProviderEvidenceReceipt(
        receipt_id=receipt_id,
        evidence_id=evidence_id,
        decision_target=registration.decision_target,
        provider_id=provider_id,
        model_id=model_id,
        agent_id=agent_id,
        scenario_id=scenario_id,
        harness_revision=harness_revision,
        status=status,
        registry_entry_digest=_registry_digest(registration),
        dependency_scope=registration.dependency_scope,
        rerun_check_ids=registration.check_ids,
        owner_id=registration.owner_id,
        event_count=event_count,
        event_type_counts=dict(sorted(event_type_counts.items())),
        tool_call_count=tool_call_count,
        evidence_id_count=evidence_id_count,
        transport_status=transport_status,
        semantic_outcome=semantic_outcome,
        usage=usage,
        refusal_code=refusal_code,
        receipt_digest=receipt_digest,
    )


def build_provider_evidence_report(
    runs: Sequence[tuple[str, AdapterRun]],
    *,
    evidence_id: str,
    model_ids: Mapping[str, str],
    harness_revision: str,
    registration: EvidenceRegistration,
) -> ProviderEvidenceReceiptReport:
    """Build receipts for multiple provider-shaped runs."""

    receipts = tuple(
        build_provider_evidence_receipt(
            run,
            evidence_id=evidence_id,
            provider_id=provider_id,
            model_id=model_ids[provider_id],
            harness_revision=harness_revision,
            registration=registration,
        )
        for provider_id, run in runs
    )
    return ProviderEvidenceReceiptReport(receipts=receipts)


__all__ = [
    "PROVIDER_RECEIPT_VERSION",
    "RECEIPT_ACCEPTED",
    "RECEIPT_BLOCKED",
    "RECEIPT_REFUSED",
    "ProviderEvidenceReceipt",
    "ProviderEvidenceReceiptReport",
    "build_provider_evidence_receipt",
    "build_provider_evidence_report",
]
