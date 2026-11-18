"""Bind synthetic shadow receipts to provider-shaped runs and reauthorization.

Design rules:

1. OpenAI- and Anthropic-shaped proposals use one action contract.
2. The existing run-manifest evaluator remains the only reauthorization rule.
3. Binding, shadow, and revision decisions remain separate in the report.
4. A blocked or human-review shadow result cannot become reusable evidence just
   because the manifest revisions are current.
5. This module handles identifiers and digests only; it never handles provider
   content or invokes an external tool.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .run_manifest import (
    RUN_MANIFEST_STATUS_BLOCKED,
    RUN_MANIFEST_STATUS_REAUTHORIZED,
    RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED,
    RunManifest,
    evaluate_reauthorization,
    load_manifest,
)
from .shadow_execution import (
    ShadowCase,
    ShadowDecision,
    ShadowReceipt,
    ShadowRefusal,
    run_shadow_case,
    shadow_case_from_dict,
)


SHADOW_REAUTHORIZATION_VERSION = 1
SHADOW_STATUS_REAUTHORIZED = "reauthorized"
SHADOW_STATUS_REAUTHORIZATION_REQUIRED = "reauthorization_required"
SHADOW_STATUS_BLOCKED = "blocked"
SHADOW_STATUS_HUMAN_REVIEW = "human_review"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_PROVIDERS = frozenset({"openai", "anthropic"})
_STATUSES = frozenset(
    {
        SHADOW_STATUS_REAUTHORIZED,
        SHADOW_STATUS_REAUTHORIZATION_REQUIRED,
        SHADOW_STATUS_BLOCKED,
        SHADOW_STATUS_HUMAN_REVIEW,
    }
)


@dataclass(frozen=True)
class ProviderShadowProposal:
    """One provider-shaped proposal bound to a cloned synthetic manifest."""

    provider_id: str
    model_id: str
    agent_id: str
    manifest: RunManifest
    case: ShadowCase
    expected_current_status: str
    expected_changed_status: str


@dataclass(frozen=True)
class ShadowReuseDecision:
    """One final reuse decision for one revision map."""

    revision_set: str
    reauthorization_status: str
    final_status: str
    manifest_digest: str
    current_revisions_digest: str
    changed_dependencies: tuple[str, ...]
    reasons: tuple[str, ...]
    required_action: str

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only decision."""

        return {
            "revision_set": self.revision_set,
            "reauthorization_status": self.reauthorization_status,
            "final_status": self.final_status,
            "supports_decision": self.final_status == SHADOW_STATUS_REAUTHORIZED,
            "manifest_digest": self.manifest_digest,
            "current_revisions_digest": self.current_revisions_digest,
            "changed_dependencies": list(self.changed_dependencies),
            "reasons": list(self.reasons),
            "required_action": self.required_action,
        }


@dataclass(frozen=True)
class ProviderShadowResult:
    """The provider-neutral shadow and revision decisions for one proposal."""

    provider_id: str
    model_id: str
    agent_id: str
    run_id: str
    case_id: str
    shadow_decision: str | None
    shadow_receipt_digest: str | None
    binding_reasons: tuple[str, ...]
    current: ShadowReuseDecision
    changed: ShadowReuseDecision
    refusal: ShadowRefusal | None = None
    expected_current_status: str | None = None
    expected_changed_status: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether both declared expected statuses were produced."""

        return (
            self.refusal is None
            and self.expected_current_status == self.current.final_status
            and self.expected_changed_status == self.changed.final_status
        )

    def to_dict(self) -> dict[str, object]:
        """Return the portable provider-neutral result."""

        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "shadow_decision": self.shadow_decision,
            "shadow_receipt_digest": self.shadow_receipt_digest,
            "binding_reasons": list(self.binding_reasons),
            "current": self.current.to_dict(),
            "changed": self.changed.to_dict(),
            "refusal": self.refusal.to_dict() if self.refusal else None,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class ShadowReauthorizationReport:
    """A bounded comparison across provider-shaped shadow proposals."""

    results: tuple[ProviderShadowResult, ...]

    @property
    def passed(self) -> bool:
        """Return whether every provider proposal met its expected decisions."""

        return bool(self.results) and all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only report."""

        current_counts = _decision_counts(
            result.current.final_status for result in self.results
        )
        changed_counts = _decision_counts(
            result.changed.final_status for result in self.results
        )
        return {
            "shadow_reauthorization_version": SHADOW_REAUTHORIZATION_VERSION,
            "passed": self.passed,
            "provider_count": len(self.results),
            "decision_counts": {
                "current": current_counts,
                "changed": changed_counts,
            },
            "results": [result.to_dict() for result in self.results],
            "diagnostics": {
                "warnings": [
                    "Provider lanes use synthetic proposals and the shared "
                    "run-manifest evaluator."
                ],
                "what_it_does_not_show": (
                    "It does not show live provider behaviour, provider quality, "
                    "real tool safety, or production reauthorization."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Return a reviewer-facing summary."""

        lines = [
            "# Shadow reauthorization",
            "",
            f"- **Decision:** {'PASS' if self.passed else 'BLOCKED'}",
            "- **Providers:** OpenAI-shaped and Anthropic-shaped synthetic lanes",
            "- **Real side effects:** none",
            "",
            "| Provider | Case | Current | Changed revisions |",
            "| --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| `{result.provider_id}` | `{result.case_id}` | "
            f"`{result.current.final_status}` | "
            f"`{result.changed.final_status}` |"
            for result in self.results
        )
        lines.extend(
            [
                "",
                "The current lane shows whether the shadow receipt can be reused. "
                "The changed lane shows when revision-aware reauthorization is "
                "required. No provider content or real tool action is used.",
                "",
            ]
        )
        return "\n".join(lines)


def run_shadow_reauthorization(
    proposals: Sequence[ProviderShadowProposal],
    current_revisions: Mapping[str, str],
    changed_revisions: Mapping[str, str],
) -> ShadowReauthorizationReport:
    """Evaluate provider-shaped shadow proposals against two revision maps."""

    results = tuple(
        _evaluate_proposal(
            proposal,
            current_revisions=current_revisions,
            changed_revisions=changed_revisions,
        )
        for proposal in proposals
    )
    return ShadowReauthorizationReport(results=results)


def load_shadow_reauthorization_fixture(
    path: Path,
    *,
    repository_root: Path,
) -> tuple[ProviderShadowProposal, ...]:
    """Load a strict provider-neutral shadow fixture."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Shadow reauthorization fixture must be an object.")
    _keys(
        data,
        {
            "shadow_reauthorization_version",
            "data_class",
            "purpose",
            "base_manifest",
            "proposals",
        },
        "shadow reauthorization fixture",
    )
    if data.get("shadow_reauthorization_version") != (
        SHADOW_REAUTHORIZATION_VERSION
    ):
        raise ValueError("shadow_reauthorization_version is not supported.")
    if data.get("data_class") != "synthetic":
        raise ValueError("data_class must be synthetic.")
    _identifier(data.get("purpose"), "purpose")
    manifest_path = _confined_path(
        path.parent,
        data.get("base_manifest"),
        repository_root,
        "base_manifest",
    )
    base_manifest = load_manifest(str(manifest_path))
    raw_proposals = data.get("proposals")
    if not isinstance(raw_proposals, list) or not raw_proposals:
        raise ValueError("proposals must be a non-empty array.")

    proposals = []
    seen_providers: set[str] = set()
    for index, raw_proposal in enumerate(raw_proposals):
        proposal = _parse_proposal(
            raw_proposal,
            base_manifest,
            f"proposals[{index}]",
        )
        if proposal.provider_id in seen_providers:
            raise ValueError("proposals must contain unique providers.")
        seen_providers.add(proposal.provider_id)
        proposals.append(proposal)
    if seen_providers != _PROVIDERS:
        raise ValueError("proposals must cover openai and anthropic.")
    return tuple(proposals)


def _parse_proposal(
    value: object,
    base_manifest: RunManifest,
    context: str,
) -> ProviderShadowProposal:
    data = _object(value, context)
    _keys(
        data,
        {
            "provider_id",
            "model_id",
            "agent_id",
            "case",
            "expected_current_status",
            "expected_changed_status",
        },
        context,
    )
    provider_id = _identifier(data.get("provider_id"), f"{context}.provider_id")
    if provider_id not in _PROVIDERS:
        raise ValueError(f"{context}.provider_id is unsupported.")
    model_id = _identifier(data.get("model_id"), f"{context}.model_id")
    agent_id = _identifier(data.get("agent_id"), f"{context}.agent_id")
    current_status = _status(
        data.get("expected_current_status"),
        f"{context}.expected_current_status",
    )
    changed_status = _status(
        data.get("expected_changed_status"),
        f"{context}.expected_changed_status",
    )
    case = shadow_case_from_dict(data.get("case"), context=f"{context}.case")
    manifest = replace(
        base_manifest,
        run_id=f"shadow-{provider_id}-run",
        agent_id=agent_id,
        provider=provider_id,
        model=model_id,
    )
    return ProviderShadowProposal(
        provider_id=provider_id,
        model_id=model_id,
        agent_id=agent_id,
        manifest=manifest,
        case=case,
        expected_current_status=current_status,
        expected_changed_status=changed_status,
    )


def _evaluate_proposal(
    proposal: ProviderShadowProposal,
    *,
    current_revisions: Mapping[str, str],
    changed_revisions: Mapping[str, str],
) -> ProviderShadowResult:
    binding_reasons = _binding_reasons(proposal)
    shadow_result = (
        None if binding_reasons else run_shadow_case(proposal.case)
    )
    refusal = shadow_result.refusal if shadow_result else None
    receipt = shadow_result.receipt if shadow_result else None
    if refusal is not None:
        binding_reasons = binding_reasons + ("shadow_input_refused",)
    shadow_decision = receipt.decision.value if receipt else None
    receipt_digest = _digest(receipt.to_dict()) if receipt else None
    current = _reuse_decision(
        "current",
        proposal.manifest,
        current_revisions,
        receipt=receipt,
        binding_reasons=binding_reasons,
    )
    changed = _reuse_decision(
        "changed",
        proposal.manifest,
        changed_revisions,
        receipt=receipt,
        binding_reasons=binding_reasons,
    )
    return ProviderShadowResult(
        provider_id=proposal.provider_id,
        model_id=proposal.model_id,
        agent_id=proposal.agent_id,
        run_id=proposal.manifest.run_id,
        case_id=proposal.case.case_id,
        shadow_decision=shadow_decision,
        shadow_receipt_digest=receipt_digest,
        binding_reasons=binding_reasons,
        current=current,
        changed=changed,
        refusal=refusal,
        expected_current_status=proposal.expected_current_status,
        expected_changed_status=proposal.expected_changed_status,
    )


def _reuse_decision(
    revision_set: str,
    manifest: RunManifest,
    revisions: Mapping[str, str],
    *,
    receipt: ShadowReceipt | None,
    binding_reasons: tuple[str, ...],
) -> ShadowReuseDecision:
    reauthorization = evaluate_reauthorization(manifest, revisions)
    reasons = list(binding_reasons)
    if receipt is not None:
        reasons.extend(f"shadow:{reason}" for reason in receipt.reason_codes)
    reasons.extend(f"reauthorization:{reason}" for reason in reauthorization.reasons)
    final_status = _final_status(
        receipt,
        reauthorization.status,
        bool(binding_reasons),
    )
    if final_status == SHADOW_STATUS_REAUTHORIZED:
        required_action = "The shadow receipt remains reusable for this revision set."
    elif final_status == SHADOW_STATUS_REAUTHORIZATION_REQUIRED:
        required_action = (
            "Rerun the affected scope and record explicit reauthorization."
        )
    elif final_status == SHADOW_STATUS_HUMAN_REVIEW:
        required_action = "Obtain human review before allowing the proposed action."
    else:
        required_action = "Repair authority, evidence, or binding before continuing."
    return ShadowReuseDecision(
        revision_set=revision_set,
        reauthorization_status=reauthorization.status,
        final_status=final_status,
        manifest_digest=reauthorization.manifest_digest,
        current_revisions_digest=reauthorization.current_revisions_digest,
        changed_dependencies=reauthorization.changed_dependencies,
        reasons=tuple(dict.fromkeys(reasons)),
        required_action=required_action,
    )


def _final_status(
    receipt: ShadowReceipt | None,
    reauthorization_status: str,
    binding_failed: bool,
) -> str:
    if binding_failed or receipt is None:
        return SHADOW_STATUS_BLOCKED
    if receipt.decision is ShadowDecision.BLOCK:
        return SHADOW_STATUS_BLOCKED
    if receipt.decision is ShadowDecision.HUMAN_REVIEW:
        return SHADOW_STATUS_HUMAN_REVIEW
    if reauthorization_status == RUN_MANIFEST_STATUS_BLOCKED:
        return SHADOW_STATUS_BLOCKED
    if reauthorization_status == RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED:
        return SHADOW_STATUS_REAUTHORIZATION_REQUIRED
    if reauthorization_status == RUN_MANIFEST_STATUS_REAUTHORIZED:
        return SHADOW_STATUS_REAUTHORIZED
    return SHADOW_STATUS_BLOCKED


def _binding_reasons(proposal: ProviderShadowProposal) -> tuple[str, ...]:
    reasons: list[str] = []
    if proposal.manifest.provider != proposal.provider_id:
        reasons.append("provider_manifest_mismatch")
    if proposal.manifest.model != proposal.model_id:
        reasons.append("model_manifest_mismatch")
    if proposal.manifest.agent_id != proposal.agent_id:
        reasons.append("agent_manifest_mismatch")
    if proposal.case.action.tool_name not in proposal.manifest.tool_scope:
        reasons.append("action_tool_outside_manifest_scope")
    if (
        proposal.case.action.policy_revision
        != proposal.manifest.revisions["policy"]
    ):
        reasons.append("action_policy_revision_mismatch")
    return tuple(reasons)


def _decision_counts(values: Sequence[str]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(_STATUSES)}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _confined_path(
    base: Path,
    value: object,
    root: Path,
    field: str,
) -> Path:
    relative = _identifier(value, field)
    candidate = (base / relative).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"{field} must remain under the repository root.") from error
    return candidate


def _status(value: object, field: str) -> str:
    result = _identifier(value, field)
    if result not in _STATUSES:
        raise ValueError(f"{field} is unsupported.")
    return result


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object.")
    return value


def _keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    if set(value) - allowed:
        raise ValueError(f"{context} contains unknown fields.")


def _identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{context} must be an identifier.")
    return value


__all__ = [
    "SHADOW_REAUTHORIZATION_VERSION",
    "SHADOW_STATUS_BLOCKED",
    "SHADOW_STATUS_HUMAN_REVIEW",
    "SHADOW_STATUS_REAUTHORIZED",
    "SHADOW_STATUS_REAUTHORIZATION_REQUIRED",
    "ProviderShadowProposal",
    "ProviderShadowResult",
    "ShadowReauthorizationReport",
    "ShadowReuseDecision",
    "load_shadow_reauthorization_fixture",
    "run_shadow_reauthorization",
]
