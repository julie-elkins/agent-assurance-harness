"""Metadata-only drift assurance for reviewed provider response contracts.

Design rules:

1. Checked-in provider fixtures are fingerprinted by raw bytes and JSON shape.
2. The reviewed live-response extractor and safe translator must accept each
   positive fixture.
3. Negative fixtures must be refused without returning raw provider content.
4. Reports contain hashes, identifiers, and refusal codes only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .live import extract_provider_payload
from .providers import ProviderPayloadError, translate_provider_payload


PROVIDER_CONTRACT_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROVIDERS = frozenset({"openai", "anthropic"})
_USAGE = {
    "requests": 1,
    "output_tokens": 32,
    "elapsed_seconds": 0.01,
    "estimated_cost_usd": 0.001,
}


@dataclass(frozen=True)
class ProviderContract:
    """One approved positive provider fixture and its fingerprints."""

    provider_id: str
    fixture: str
    fixture_sha256: str
    shape_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "fixture": self.fixture,
            "fixture_sha256": self.fixture_sha256,
            "shape_sha256": self.shape_sha256,
        }


@dataclass(frozen=True)
class ProviderContractResult:
    """The result of checking one positive fixture."""

    provider_id: str
    fixture: str
    fixture_sha256: str
    shape_sha256: str
    passed: bool
    refusal_code: str | None
    drift_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "fixture": self.fixture,
            "fixture_sha256": self.fixture_sha256,
            "shape_sha256": self.shape_sha256,
            "passed": self.passed,
            "refusal_code": self.refusal_code,
            "drift_reasons": list(self.drift_reasons),
        }


@dataclass(frozen=True)
class ProviderContractNegativeControl:
    """One fixture that must be refused by the reviewed parser."""

    provider_id: str
    fixture: str
    expected_error: str
    caught: bool
    observed_error: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "fixture": self.fixture,
            "expected_error": self.expected_error,
            "caught": self.caught,
            "observed_error": self.observed_error,
        }


@dataclass(frozen=True)
class ProviderContractReport:
    """The public, metadata-only provider contract drift result."""

    contracts: tuple[ProviderContractResult, ...]
    negative_controls: tuple[ProviderContractNegativeControl, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.contracts) and all(
            item.caught for item in self.negative_controls
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_contract_version": PROVIDER_CONTRACT_VERSION,
            "passed": self.passed,
            "contracts": [item.to_dict() for item in self.contracts],
            "negative_controls": [
                item.to_dict() for item in self.negative_controls
            ],
            "diagnostics": {
                "warnings": [
                    "A contract fingerprint detects reviewed fixture drift; it "
                    "does not establish live provider availability or quality.",
                    "Fixture names, hashes, and refusal codes are metadata only; "
                    "provider content is not included.",
                ],
                "what_it_does_not_show": (
                    "It does not show prompts, provider requests or responses, "
                    "model text, credentials, or production monitoring."
                ),
            },
        }

    def to_markdown(self) -> str:
        lines = [
            "# Provider contract drift gate",
            "",
            f"- **Decision:** {'PASS' if self.passed else 'BLOCKED'}",
            "- **Network:** disabled; checked-in fixtures only",
            "",
            "## Approved contracts",
            "",
            "| Provider | Fixture | Result | Fixture SHA-256 | Shape SHA-256 |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| `{item.provider_id}` | `{item.fixture}` | "
            f"{'PASS' if item.passed else 'DRIFT'} | "
            f"`{item.fixture_sha256}` | `{item.shape_sha256}` |"
            for item in self.contracts
        )
        lines.extend(
            [
                "",
                "## Negative controls",
                "",
                "| Provider | Fixture | Result | Expected refusal | Observed refusal |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| `{item.provider_id}` | `{item.fixture}` | "
            f"{'CAUGHT' if item.caught else 'MISSED'} | "
            f"`{item.expected_error}` | `{item.observed_error or 'none'}` |"
            for item in self.negative_controls
        )
        lines.extend(
            [
                "",
                "Provider output, prompts, credentials, and raw payloads are "
                "excluded from this summary.",
                "",
            ]
        )
        return "\n".join(lines)


def load_provider_contract_manifest(path: Path) -> tuple[
    tuple[ProviderContract, ...],
    tuple[ProviderContractNegativeControl, ...],
]:
    """Load and strictly validate the checked-in contract manifest."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Provider contract manifest must be an object.")
    if set(data) - {
        "provider_contract_version",
        "contracts",
        "negative_controls",
    }:
        raise ValueError("Provider contract manifest contains unknown fields.")
    if data.get("provider_contract_version") != PROVIDER_CONTRACT_VERSION:
        raise ValueError("provider_contract_version is not supported.")
    contracts = tuple(
        _parse_contract(item)
        for item in _list(data.get("contracts"), "contracts")
    )
    negative_controls = tuple(
        _parse_negative(item)
        for item in _list(data.get("negative_controls"), "negative_controls")
    )
    if {item.provider_id for item in contracts} != _PROVIDERS:
        raise ValueError("Positive contracts must cover openai and anthropic.")
    if not negative_controls:
        raise ValueError("At least one negative control is required.")
    return contracts, negative_controls


def run_provider_contract_assurance(
    manifest_path: Path,
    fixture_root: Path,
) -> ProviderContractReport:
    """Fingerprint and translate the approved positive and negative fixtures."""

    contracts, negative_controls = load_provider_contract_manifest(manifest_path)
    positive_results = tuple(
        _check_contract(contract, fixture_root)
        for contract in contracts
    )
    negative_results = tuple(
        _check_negative_control(control, fixture_root)
        for control in negative_controls
    )
    return ProviderContractReport(
        contracts=positive_results,
        negative_controls=negative_results,
    )


def _check_contract(
    contract: ProviderContract,
    fixture_root: Path,
) -> ProviderContractResult:
    raw, data = _read_fixture(contract.fixture, fixture_root)
    fixture_sha = _sha256(raw)
    shape_sha = _shape_sha256(data)
    drift_reasons: list[str] = []
    if fixture_sha != contract.fixture_sha256:
        drift_reasons.append("fixture-sha256-mismatch")
    if shape_sha != contract.shape_sha256:
        drift_reasons.append("shape-sha256-mismatch")
    refusal_code: str | None = None
    try:
        payload = extract_provider_payload(contract.provider_id, data)
        safe_payload = dict(payload)
        safe_payload["usage"] = dict(_USAGE)
        if contract.provider_id == "anthropic":
            safe_payload["stop_reason"] = "end_turn"
        translated = translate_provider_payload(
            contract.provider_id,
            safe_payload,
            scenario_id="provider-contract-fixture",
            agent_id=f"{contract.provider_id}-contract",
        )
        if translated.refusal is not None:
            refusal_code = translated.refusal.error
    except ProviderPayloadError as error:
        refusal_code = error.error
    if refusal_code is not None:
        drift_reasons.append("positive-fixture-refused")
    return ProviderContractResult(
        provider_id=contract.provider_id,
        fixture=contract.fixture,
        fixture_sha256=fixture_sha,
        shape_sha256=shape_sha,
        passed=not drift_reasons,
        refusal_code=refusal_code,
        drift_reasons=tuple(drift_reasons),
    )


def _check_negative_control(
    control: ProviderContractNegativeControl,
    fixture_root: Path,
) -> ProviderContractNegativeControl:
    _, data = _read_fixture(control.fixture, fixture_root)
    observed_error: str | None = None
    try:
        payload = extract_provider_payload(control.provider_id, data)
        safe_payload = dict(payload)
        safe_payload["usage"] = dict(_USAGE)
        if control.provider_id == "anthropic":
            safe_payload["stop_reason"] = "end_turn"
        translated = translate_provider_payload(
            control.provider_id,
            safe_payload,
            scenario_id="provider-contract-negative",
            agent_id=f"{control.provider_id}-contract-negative",
        )
        if translated.refusal is not None:
            observed_error = translated.refusal.error
    except ProviderPayloadError as error:
        observed_error = error.error
    return ProviderContractNegativeControl(
        provider_id=control.provider_id,
        fixture=control.fixture,
        expected_error=control.expected_error,
        caught=observed_error == control.expected_error,
        observed_error=observed_error,
    )


def _parse_contract(value: object) -> ProviderContract:
    if not isinstance(value, dict):
        raise ValueError("Each provider contract must be an object.")
    if set(value) - {
        "provider_id",
        "fixture",
        "fixture_sha256",
        "shape_sha256",
    }:
        raise ValueError("Provider contracts contain unknown fields.")
    return ProviderContract(
        provider_id=_provider(value.get("provider_id")),
        fixture=_fixture_name(value.get("fixture")),
        fixture_sha256=_hash(value.get("fixture_sha256"), "fixture_sha256"),
        shape_sha256=_hash(value.get("shape_sha256"), "shape_sha256"),
    )


def _parse_negative(value: object) -> ProviderContractNegativeControl:
    if not isinstance(value, dict):
        raise ValueError("Each provider negative control must be an object.")
    if set(value) - {"provider_id", "fixture", "expected_error"}:
        raise ValueError("Provider negative controls contain unknown fields.")
    return ProviderContractNegativeControl(
        provider_id=_provider(value.get("provider_id")),
        fixture=_fixture_name(value.get("fixture")),
        expected_error=_identifier(value.get("expected_error"), "expected_error"),
        caught=False,
        observed_error=None,
    )


def _read_fixture(name: str, root: Path) -> tuple[bytes, dict[str, Any]]:
    path = root / name
    if path.parent != root:
        raise ValueError("Provider fixture must be a direct child of its fixture root.")
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Provider fixture must contain a JSON object.")
    return raw, data


def _shape_sha256(value: object) -> str:
    shape = _shape(value)
    return _sha256(json.dumps(shape, sort_keys=True, separators=(",", ":")).encode())


def _shape(value: object) -> object:
    if isinstance(value, dict):
        return {
            "object": {
                str(key): _shape(item)
                for key, item in sorted(value.items())
            }
        }
    if isinstance(value, list):
        return {"array": [_shape(item) for item in value]}
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    raise ValueError("Provider fixture contains an unsupported JSON value.")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list.")
    return value


def _provider(value: object) -> str:
    provider = _identifier(value, "provider_id")
    if provider not in _PROVIDERS:
        raise ValueError("provider_id must be openai or anthropic.")
    return provider


def _fixture_name(value: object) -> str:
    fixture = _identifier(value, "fixture")
    if "/" in fixture or not fixture.endswith(".json"):
        raise ValueError("fixture must be a direct JSON filename.")
    return fixture


def _hash(value: object, field: str) -> str:
    result = _identifier(value, field)
    if _SHA256.fullmatch(result) is None:
        raise ValueError(f"{field} must be a SHA-256 hash.")
    return result


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field} must be a non-empty identifier.")
    return value
