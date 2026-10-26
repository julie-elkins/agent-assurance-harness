"""Change-impact planning for provider-neutral agent evidence.

This module answers a narrow question: which previously recorded evidence must be
rerun after declared revisions or repository paths change? It never inspects prompts,
tool payloads, provider output, credentials, or private traces.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .evidence_registry import EvidenceRegistration
from .run_manifest import (
    REQUIRED_REVISION_KEYS,
    RUN_MANIFEST_STATUS_BLOCKED,
    RunManifest,
    RunManifestValidationError,
    evaluate_reauthorization,
)


CHANGE_IMPACT_VERSION = 1
IMPACT_READY = "evidence_still_valid"
IMPACT_RERUN_REQUIRED = "rerun_required"
IMPACT_BLOCKED = "blocked"

_DEPENDENCY_PREFIXES = frozenset(REQUIRED_REVISION_KEYS)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _path_dependencies(path: str) -> tuple[str, ...]:
    """Map a public repository path to conservative manifest dependencies."""

    normalized = path.replace("\\", "/").lstrip("./")
    if not normalized:
        return ()
    if (
        normalized in {"README.md", "DESIGN_DECISIONS.md"}
        or normalized.startswith("docs/")
        or normalized.startswith("examples/change-impact/")
    ):
        return ()
    if normalized.startswith("prompts/") or "prompt" in normalized:
        return ("prompt",)
    if normalized.startswith("examples/") and (
        "data" in normalized or "scenario" in normalized or "pack" in normalized
    ):
        return ("data",)
    if "policy" in normalized or "authorization" in normalized:
        return ("policy",)
    if "grader" in normalized or "evaluator" in normalized:
        return ("grader",)
    if normalized.startswith("tests/"):
        return ("grader",)
    if "openai" in normalized or "claude" in normalized or "provider" in normalized:
        return ("model", "harness")
    if normalized.startswith(".github/"):
        return ("environment",)
    if normalized.startswith("schemas/"):
        return ("harness",)
    if normalized.startswith("tools/"):
        return ("harness",)
    if normalized.startswith("src/"):
        return ("harness",)
    if normalized in {"pyproject.toml", "uv.lock", "template.yaml"}:
        return ("environment", "repository")
    return ("repository",)


def classify_paths(paths: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Return deterministic path-to-dependency classifications."""

    result: dict[str, tuple[str, ...]] = {}
    for path in sorted(set(paths)):
        dependencies = _path_dependencies(path)
        if dependencies:
            result[path] = dependencies
    return result


def _validate_revisions(
    revisions: Mapping[str, str], field: str
) -> dict[str, str]:
    keys = set(revisions)
    missing = sorted(_DEPENDENCY_PREFIXES - keys)
    extra = sorted(keys - _DEPENDENCY_PREFIXES)
    errors: list[str] = []
    if missing:
        errors.append(f"{field} missing: {', '.join(missing)}")
    if extra:
        errors.append(f"{field} contains unsupported keys: {', '.join(extra)}")
    normalized: dict[str, str] = {}
    for key in REQUIRED_REVISION_KEYS:
        if key in revisions:
            value = revisions[key]
            if not isinstance(value, str) or not value.strip() or any(
                character.isspace() for character in value
            ):
                errors.append(f"{field}.{key} must be a non-empty identifier")
            else:
                normalized[key] = value
    if errors:
        raise RunManifestValidationError(tuple(errors))
    return normalized


@dataclass(frozen=True)
class EvidenceImpact:
    """Impact decision for one existing evidence manifest."""

    evidence_id: str
    decision_target: str
    status: str
    changed_dependencies: tuple[str, ...]
    changed_paths: tuple[str, ...]
    rerun_checks: tuple[str, ...]
    owner_id: str | None
    reasons: tuple[str, ...]
    required_action: str

    @property
    def supports_decision(self) -> bool:
        return self.status == IMPACT_READY

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "decision_target": self.decision_target,
            "status": self.status,
            "supports_decision": self.status == IMPACT_READY,
            "changed_dependencies": list(self.changed_dependencies),
            "changed_paths": list(self.changed_paths),
            "rerun_checks": list(self.rerun_checks),
            "owner_id": self.owner_id,
            "reasons": list(self.reasons),
            "required_action": self.required_action,
        }


@dataclass(frozen=True)
class ChangeImpactPlan:
    """Metadata-only rerun plan for one change set."""

    changed_paths: tuple[str, ...]
    path_classifications: dict[str, tuple[str, ...]]
    changed_dependencies: tuple[str, ...]
    baseline_revisions_digest: str
    current_revisions_digest: str
    evidence: tuple[EvidenceImpact, ...]
    status: str

    @property
    def failed(self) -> bool:
        return self.status != IMPACT_READY

    def to_dict(self) -> dict[str, object]:
        return {
            "change_impact_version": CHANGE_IMPACT_VERSION,
            "status": self.status,
            "failed": self.failed,
            "changed_paths": list(self.changed_paths),
            "path_classifications": {
                path: list(dependencies)
                for path, dependencies in self.path_classifications.items()
            },
            "changed_dependencies": list(self.changed_dependencies),
            "baseline_revisions_digest": self.baseline_revisions_digest,
            "current_revisions_digest": self.current_revisions_digest,
            "evidence": [item.to_dict() for item in self.evidence],
            "required_action": (
                "Rerun every affected evidence scope and record reauthorization."
                if self.failed
                else "No affected evidence was found; existing evidence remains usable."
            ),
        }

    def to_markdown(self) -> str:
        data = self.to_dict()
        lines = [
            "## Agent change-impact plan",
            "",
            f"- **Decision:** `{data['status']}`",
            f"- **Changed dependencies:** "
            f"{', '.join(data['changed_dependencies']) or 'none'}",
            f"- **Changed paths:** {len(data['changed_paths'])}",
            "",
            "### Evidence decisions",
            "",
        ]
        for item in self.evidence:
            lines.extend(
                [
                    f"- `{item.evidence_id}` — **{item.status}** "
                    f"({item.decision_target})",
                    f"  - Changed dependencies: "
                    f"{', '.join(item.changed_dependencies) or 'none'}",
                    f"  - Rerun checks: "
                    f"{', '.join(item.rerun_checks) or 'register or review manually'}",
                    f"  - Owner: {item.owner_id or 'unassigned'}",
                    f"  - Action: {item.required_action}",
                ]
            )
        lines.extend(
            [
                "",
                f"**Required action:** {data['required_action']}",
                "",
                "This report contains identifiers, revisions, paths, states, and "
                "reason codes only; it does not prove live model quality.",
                "",
            ]
        )
        return "\n".join(lines)


def build_change_impact_plan(
    manifests: Sequence[RunManifest],
    baseline_revisions: Mapping[str, str],
    current_revisions: Mapping[str, str],
    changed_paths: Iterable[str] = (),
    registry: Mapping[str, EvidenceRegistration] | None = None,
) -> ChangeImpactPlan:
    """Build a conservative impact plan from manifests and safe change metadata."""

    baseline = _validate_revisions(baseline_revisions, "baseline_revisions")
    current = _validate_revisions(current_revisions, "current_revisions")
    normalized_paths = tuple(sorted(set(path for path in changed_paths if path)))
    classifications = classify_paths(normalized_paths)
    revision_changes = {
        key for key in REQUIRED_REVISION_KEYS if baseline[key] != current[key]
    }
    path_changes = {
        dependency
        for dependencies in classifications.values()
        for dependency in dependencies
    }
    changed_dependencies = tuple(
        key
        for key in REQUIRED_REVISION_KEYS
        if key in revision_changes or key in path_changes
    )

    evidence: list[EvidenceImpact] = []
    for manifest in manifests:
        decision = evaluate_reauthorization(manifest, current)
        registration = registry.get(manifest.run_id) if registry is not None else None
        evidence_scope = (
            set(registration.dependency_scope)
            if registration is not None
            else set(REQUIRED_REVISION_KEYS)
        )
        impacted_dependencies = tuple(
            dependency
            for dependency in changed_dependencies
            if dependency in evidence_scope
        )
        manifest_paths = tuple(
            path
            for path, dependencies in classifications.items()
            if set(dependencies) & set(impacted_dependencies)
        )
        impacted = bool(impacted_dependencies)
        if decision.status == RUN_MANIFEST_STATUS_BLOCKED:
            status = IMPACT_BLOCKED
            reasons = ("existing_evidence_blocked",) + decision.reasons
            action = "Repair or replace blocked evidence before using this decision."
            rerun_checks = registration.check_ids if registration else ()
            owner_id = registration.owner_id if registration else None
        elif impacted and registry is not None and registration is None:
            status = IMPACT_BLOCKED
            reasons = ("evidence_registry_missing",)
            action = "Register rerun checks and dependency scope before continuing."
            rerun_checks = ()
            owner_id = None
        elif impacted:
            status = IMPACT_RERUN_REQUIRED
            reasons = tuple(
                f"changed_dependency:{dependency}"
                for dependency in impacted_dependencies
            )
            rerun_checks = registration.check_ids if registration else ()
            owner_id = registration.owner_id if registration else None
            action = (
                "Run the listed checks and record reauthorization."
                if rerun_checks
                else "Rerun the affected evidence scope and record reauthorization."
            )
        else:
            status = IMPACT_READY
            reasons = ()
            action = "Existing evidence remains usable for this change set."
            rerun_checks = ()
            owner_id = registration.owner_id if registration else None
        evidence.append(
            EvidenceImpact(
                evidence_id=manifest.run_id,
                decision_target=manifest.decision_target,
                status=status,
                changed_dependencies=tuple(
                    dependency
                    for dependency in impacted_dependencies
                )
                if impacted
                else (),
                changed_paths=manifest_paths if impacted else (),
                rerun_checks=rerun_checks,
                owner_id=owner_id,
                reasons=reasons,
                required_action=action,
            )
        )

    statuses = {item.status for item in evidence}
    status = (
        IMPACT_BLOCKED
        if IMPACT_BLOCKED in statuses
        else IMPACT_RERUN_REQUIRED
        if IMPACT_RERUN_REQUIRED in statuses
        else IMPACT_READY
    )
    return ChangeImpactPlan(
        changed_paths=normalized_paths,
        path_classifications=classifications,
        changed_dependencies=changed_dependencies,
        baseline_revisions_digest=_digest(baseline),
        current_revisions_digest=_digest(current),
        evidence=tuple(evidence),
        status=status,
    )


__all__ = [
    "CHANGE_IMPACT_VERSION",
    "IMPACT_BLOCKED",
    "IMPACT_READY",
    "IMPACT_RERUN_REQUIRED",
    "ChangeImpactPlan",
    "EvidenceImpact",
    "build_change_impact_plan",
    "classify_paths",
]
