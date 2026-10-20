"""Pack provenance and canonical fingerprints.

Design rules:

1. A manifest identifies the exact validated pack definition, not a caller path.
2. Hashing uses canonical JSON so equivalent key ordering produces one fingerprint.
3. Manifests contain metadata and identifiers only; they never contain traces or payloads.
4. The hash is evidence of pack identity, not evidence that the pack is a good test.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from .packs import ScenarioPack


PACK_HASH_ALGORITHM = "sha256"
_PACKAGE_NAME = "agent-reliability-lab"


@dataclass(frozen=True)
class PackManifest:
    """Metadata needed to identify one evaluated scenario pack."""

    scenario_id: str
    pack_version: int
    pack_sha256: str
    pack_hash_algorithm: str
    harness_version: str
    owner: str
    purpose: str
    data_class: str

    def to_dict(self) -> dict[str, object]:
        """Return an identifier-only provenance record."""

        return {
            "scenario_id": self.scenario_id,
            "pack_version": self.pack_version,
            "pack_sha256": self.pack_sha256,
            "pack_hash_algorithm": self.pack_hash_algorithm,
            "harness_version": self.harness_version,
            "owner": self.owner,
            "purpose": self.purpose,
            "data_class": self.data_class,
        }


def pack_sha256(pack: ScenarioPack) -> str:
    """Return the hash of the canonical validated pack definition."""

    encoded = json.dumps(
        pack.to_dict(),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def pack_manifest(pack: ScenarioPack) -> PackManifest:
    """Build provenance metadata for one validated pack."""

    return PackManifest(
        scenario_id=pack.scenario_id,
        pack_version=pack.pack_version,
        pack_sha256=pack_sha256(pack),
        pack_hash_algorithm=PACK_HASH_ALGORITHM,
        harness_version=_harness_version(),
        owner=pack.metadata.owner,
        purpose=pack.metadata.purpose,
        data_class=pack.metadata.data_class,
    )


def _harness_version() -> str:
    """Return the installed harness version without inventing a source version."""

    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "source-checkout"


def pack_set_sha256(packs: tuple[ScenarioPack, ...]) -> str:
    """Return the hash of the sorted canonical pack set."""

    encoded = json.dumps(
        [
            pack.to_dict()
            for pack in sorted(packs, key=lambda item: item.scenario_id)
        ],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "PACK_HASH_ALGORITHM",
    "PackManifest",
    "pack_manifest",
    "pack_set_sha256",
    "pack_sha256",
]
