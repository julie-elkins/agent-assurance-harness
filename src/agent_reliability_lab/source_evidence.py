"""Strict, metadata-only source-evidence receipts.

The receipt records what source was checked, when, within what scope, and what
the check supports. It deliberately has no claim text, source body, prompt,
tool payload, or executable rerun command.

This is a report-only contract. ``human_disposition`` remains
``pending_review`` until a person decides whether the evidence may affect a
review outcome.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from .run_manifest import RunManifestValidationError


SOURCE_EVIDENCE_RECEIPT_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCOPE_KEYS = frozenset(
    {
        "account_scope",
        "api_version",
        "guide_version",
        "media_type",
        "partition",
        "region",
        "service",
        "source_role",
    }
)
LOOKUP_STATUSES = frozenset(
    {"completed", "not_checked", "unavailable", "refused", "failed"}
)
SUPPORT_STATUSES = frozenset(
    {"supports", "contradicts", "insufficient", "conflict", "not_evaluated"}
)
HUMAN_DISPOSITIONS = frozenset(
    {"pending_review", "accepted", "rejected", "needs_review"}
)


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunManifestValidationError((f"{field} must be a non-empty string",))
    if _IDENTIFIER.fullmatch(value) is None:
        raise RunManifestValidationError(
            (f"{field} must contain only identifier characters",)
        )
    return value


def _optional_identifier(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field)


def _timestamp(value: object, field: str, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise RunManifestValidationError((f"{field} is required",))
        return None
    if not isinstance(value, str) or not value.strip():
        raise RunManifestValidationError((f"{field} must be an ISO date or datetime",))
    candidate = value.replace("Z", "+00:00")
    try:
        if "T" in candidate:
            datetime.fromisoformat(candidate)
        else:
            date.fromisoformat(candidate)
    except ValueError as exc:
        raise RunManifestValidationError(
            (f"{field} must be an ISO date or datetime",)
        ) from exc
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise RunManifestValidationError(
            (f"{field} must be a sha256: digest",)
        )
    return value


@dataclass(frozen=True)
class SourceEvidenceReceipt:
    """One source check with a human-review boundary."""

    receipt_id: str
    evidence_id: str
    claim_id: str
    source_id: str
    authority: str
    source_url: str
    source_locator: str | None
    retrieved_at: str
    document_updated_at: str | None
    source_digest: str
    scope: Mapping[str, str]
    lookup_status: str
    support_status: str
    human_disposition: str
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return the metadata-only wire shape."""

        return {
            "source_evidence_receipt_version": SOURCE_EVIDENCE_RECEIPT_VERSION,
            "receipt_id": self.receipt_id,
            "evidence_id": self.evidence_id,
            "claim_id": self.claim_id,
            "source_id": self.source_id,
            "authority": self.authority,
            "source_url": self.source_url,
            "source_locator": self.source_locator,
            "retrieved_at": self.retrieved_at,
            "document_updated_at": self.document_updated_at,
            "source_digest": self.source_digest,
            "scope": dict(sorted(self.scope.items())),
            "lookup_status": self.lookup_status,
            "support_status": self.support_status,
            "human_disposition": self.human_disposition,
            "limitations": list(self.limitations),
            "what_it_does_not_show": (
                "This receipt does not prove the item or claim is correct, "
                "does not contain source text, and does not authorize changing "
                "a review outcome."
            ),
        }

    @classmethod
    def from_dict(cls, value: object) -> "SourceEvidenceReceipt":
        """Strictly load one receipt and reject content-bearing additions."""

        if not isinstance(value, dict):
            raise RunManifestValidationError(("source evidence receipt must be an object",))
        allowed = {
            "source_evidence_receipt_version",
            "receipt_id",
            "evidence_id",
            "claim_id",
            "source_id",
            "authority",
            "source_url",
            "source_locator",
            "retrieved_at",
            "document_updated_at",
            "source_digest",
            "scope",
            "lookup_status",
            "support_status",
            "human_disposition",
            "limitations",
            "what_it_does_not_show",
        }
        extra = sorted(set(value) - allowed)
        if extra:
            raise RunManifestValidationError(
                ("source evidence receipt contains unsupported keys: " + ", ".join(extra),)
            )
        if value.get("source_evidence_receipt_version") != SOURCE_EVIDENCE_RECEIPT_VERSION:
            raise RunManifestValidationError(
                (
                    "source_evidence_receipt_version must be "
                    f"{SOURCE_EVIDENCE_RECEIPT_VERSION}",
                )
            )
        url = value.get("source_url")
        parsed = urlparse(url) if isinstance(url, str) else None
        if (
            parsed is None
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise RunManifestValidationError(
                ("source_url must be an https URL without credentials",)
            )
        scope = value.get("scope")
        if not isinstance(scope, dict):
            raise RunManifestValidationError(("scope must be an object",))
        if any(
            not isinstance(key, str)
            or key not in _SCOPE_KEYS
            or not isinstance(item, str)
            or not item.strip()
            for key, item in scope.items()
        ):
            raise RunManifestValidationError(
                ("scope keys and values must use the bounded metadata vocabulary",)
            )
        limitations = value.get("limitations")
        if not isinstance(limitations, list) or any(
            not isinstance(item, str) or not item.strip() for item in limitations
        ):
            raise RunManifestValidationError(
                ("limitations must be an array of non-empty strings",)
            )
        what_it_does_not_show = value.get("what_it_does_not_show")
        if (
            not isinstance(what_it_does_not_show, str)
            or not what_it_does_not_show.strip()
        ):
            raise RunManifestValidationError(
                ("what_it_does_not_show must be a non-empty string",)
            )
        lookup_status = value.get("lookup_status")
        support_status = value.get("support_status")
        disposition = value.get("human_disposition")
        if lookup_status not in LOOKUP_STATUSES:
            raise RunManifestValidationError(
                (f"lookup_status must be one of {sorted(LOOKUP_STATUSES)}",)
            )
        if support_status not in SUPPORT_STATUSES:
            raise RunManifestValidationError(
                (f"support_status must be one of {sorted(SUPPORT_STATUSES)}",)
            )
        if disposition not in HUMAN_DISPOSITIONS:
            raise RunManifestValidationError(
                (f"human_disposition must be one of {sorted(HUMAN_DISPOSITIONS)}",)
            )
        if lookup_status != "completed" and support_status != "not_evaluated":
            raise RunManifestValidationError(
                (
                    "a lookup that did not complete must use "
                    "support_status=not_evaluated",
                )
            )
        return cls(
            receipt_id=_identifier(value.get("receipt_id"), "receipt_id"),
            evidence_id=_identifier(value.get("evidence_id"), "evidence_id"),
            claim_id=_identifier(value.get("claim_id"), "claim_id"),
            source_id=_identifier(value.get("source_id"), "source_id"),
            authority=_identifier(value.get("authority"), "authority"),
            source_url=url,
            source_locator=_optional_identifier(
                value.get("source_locator"), "source_locator"
            ),
            retrieved_at=_timestamp(
                value.get("retrieved_at"), "retrieved_at", required=True
            )
            or "",
            document_updated_at=_timestamp(
                value.get("document_updated_at"),
                "document_updated_at",
                required=False,
            ),
            source_digest=_digest(value.get("source_digest"), "source_digest"),
            scope=dict(scope),
            lookup_status=lookup_status,
            support_status=support_status,
            human_disposition=disposition,
            limitations=tuple(limitations),
        )


def load_source_evidence_receipt(
    path: str | Path,
) -> SourceEvidenceReceipt:
    """Load one JSON receipt from a local report-only workspace."""

    with open(path, encoding="utf-8") as handle:
        return SourceEvidenceReceipt.from_dict(json.load(handle))


__all__ = [
    "HUMAN_DISPOSITIONS",
    "LOOKUP_STATUSES",
    "SOURCE_EVIDENCE_RECEIPT_VERSION",
    "SUPPORT_STATUSES",
    "SourceEvidenceReceipt",
    "load_source_evidence_receipt",
]
