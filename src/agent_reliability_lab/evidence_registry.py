"""Strict, metadata-only evidence registry for actionable rerun plans.

The registry names what a result covers and which trusted check identifiers a
reviewer should rerun. It deliberately does not contain executable commands.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .run_manifest import REQUIRED_REVISION_KEYS, RunManifestValidationError


EVIDENCE_REGISTRY_VERSION = 1
_CHECK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunManifestValidationError((f"{field} must be a non-empty string",))
    if any(character.isspace() for character in value):
        raise RunManifestValidationError((f"{field} must not contain whitespace",))
    return value


def _check_id(value: object, field: str) -> str:
    result = _identifier(value, field)
    if not _CHECK_ID.fullmatch(result):
        raise RunManifestValidationError(
            (f"{field} must be a lowercase check identifier, not a command",)
        )
    return result


@dataclass(frozen=True)
class EvidenceRegistration:
    """The safe rerun metadata for one evidence result."""

    evidence_id: str
    decision_target: str
    dependency_scope: tuple[str, ...]
    check_ids: tuple[str, ...]
    owner_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "decision_target": self.decision_target,
            "dependency_scope": list(self.dependency_scope),
            "check_ids": list(self.check_ids),
            "owner_id": self.owner_id,
        }

    @classmethod
    def from_dict(cls, value: object, index: int) -> "EvidenceRegistration":
        if not isinstance(value, dict):
            raise RunManifestValidationError(
                (f"entries[{index}] must be an object",)
            )
        allowed = {
            "evidence_id",
            "decision_target",
            "dependency_scope",
            "check_ids",
            "owner_id",
        }
        extra = sorted(set(value) - allowed)
        if extra:
            raise RunManifestValidationError(
                (f"entries[{index}] contains unsupported keys: {', '.join(extra)}",)
            )
        scope = value.get("dependency_scope")
        if not isinstance(scope, list) or not scope:
            raise RunManifestValidationError(
                (f"entries[{index}].dependency_scope must be a non-empty array",)
            )
        normalized_scope = tuple(
            _identifier(item, f"entries[{index}].dependency_scope item")
            for item in scope
        )
        unsupported = sorted(set(normalized_scope) - set(REQUIRED_REVISION_KEYS))
        if unsupported:
            raise RunManifestValidationError(
                (
                    f"entries[{index}].dependency_scope contains unsupported keys: "
                    f"{', '.join(unsupported)}",
                )
            )
        if len(set(normalized_scope)) != len(normalized_scope):
            raise RunManifestValidationError(
                (f"entries[{index}].dependency_scope must be unique",)
            )
        checks = value.get("check_ids")
        if not isinstance(checks, list) or not checks:
            raise RunManifestValidationError(
                (f"entries[{index}].check_ids must be a non-empty array",)
            )
        normalized_checks = tuple(
            _check_id(item, f"entries[{index}].check_ids item") for item in checks
        )
        if len(set(normalized_checks)) != len(normalized_checks):
            raise RunManifestValidationError(
                (f"entries[{index}].check_ids must be unique",)
            )
        return cls(
            evidence_id=_identifier(
                value.get("evidence_id"), f"entries[{index}].evidence_id"
            ),
            decision_target=_identifier(
                value.get("decision_target"),
                f"entries[{index}].decision_target",
            ),
            dependency_scope=tuple(
                key
                for key in REQUIRED_REVISION_KEYS
                if key in normalized_scope
            ),
            check_ids=normalized_checks,
            owner_id=_identifier(value.get("owner_id"), f"entries[{index}].owner_id"),
        )


def load_evidence_registry(path: str | Path) -> dict[str, EvidenceRegistration]:
    """Load and validate a registry keyed by evidence ID."""

    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RunManifestValidationError(("evidence registry must be an object",))
    allowed = {"evidence_registry_version", "entries"}
    extra = sorted(set(value) - allowed)
    if extra:
        raise RunManifestValidationError(
            ("evidence registry contains unsupported keys: " + ", ".join(extra),)
        )
    if value.get("evidence_registry_version") != EVIDENCE_REGISTRY_VERSION:
        raise RunManifestValidationError(
            (f"evidence_registry_version must be {EVIDENCE_REGISTRY_VERSION}",)
        )
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise RunManifestValidationError(
            ("evidence registry entries must be a non-empty array",)
        )
    registrations = [
        EvidenceRegistration.from_dict(entry, index)
        for index, entry in enumerate(entries)
    ]
    result: dict[str, EvidenceRegistration] = {}
    for registration in registrations:
        if registration.evidence_id in result:
            raise RunManifestValidationError(
                (f"duplicate evidence_id: {registration.evidence_id}",)
            )
        result[registration.evidence_id] = registration
    return result


def registry_from_entries(
    entries: Mapping[str, EvidenceRegistration],
) -> dict[str, EvidenceRegistration]:
    """Return a defensive copy for callers constructing synthetic registries."""

    return dict(entries)


__all__ = [
    "EVIDENCE_REGISTRY_VERSION",
    "EvidenceRegistration",
    "load_evidence_registry",
    "registry_from_entries",
]
