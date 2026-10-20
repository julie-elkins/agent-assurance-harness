"""Strict declarative scenario-pack loading.

Design rules:

1. Pack files are data, never executable instructions.
2. Unknown fields and unsupported requirement types are refusals, not ignored options.
3. Built-in packs contain synthetic identifiers only.
4. Simulator construction happens from validated values, never from imported pack code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .environment import FaultInjection, FaultMode, SimulatedToolEnvironment, ToolSpec
from .models import AssuranceDimension, EvidenceContract, EvidenceRequirement
from .protocol import ScenarioRequest


PACK_VERSION = 2
SUPPORTED_EVIDENCE_TYPES = frozenset(
    {
        "tool_call",
        "successful_tool_result",
        "authorization",
        "action_digest",
        "side_effect",
        "reconciliation",
        "output_handling",
        "agent_behaviour",
    }
)
REQUIRED_ID_PREFIXES = {
    "tool_call": "tool:",
    "successful_tool_result": "successful_tool:",
    "authorization": "authorization:",
    "action_digest": "action-digest:",
    "side_effect": "side-effect:",
    "reconciliation": "reconciliation:",
    "output_handling": "output:",
    "agent_behaviour": "abstain:",
}


@dataclass(frozen=True)
class PackRefusal:
    """A structured refusal for an invalid or unreadable scenario pack."""

    error: str
    message: str
    guidance: str
    source: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe refusal."""

        return {
            "error": self.error,
            "message": self.message,
            "guidance": self.guidance,
            "source": self.source,
        }


@dataclass(frozen=True)
class PackResult:
    """Exactly one validated pack or one structured refusal."""

    pack: "ScenarioPack | None" = None
    refusal: PackRefusal | None = None


@dataclass(frozen=True)
class PackMetadata:
    """Required provenance metadata for one public synthetic pack."""

    owner: str
    purpose: str
    data_class: str

    def to_dict(self) -> dict[str, str]:
        """Return metadata without content-bearing scenario data."""

        return {
            "owner": self.owner,
            "purpose": self.purpose,
            "data_class": self.data_class,
        }


@dataclass(frozen=True)
class ScenarioPack:
    """A versioned synthetic scenario contract and simulator definition."""

    pack_version: int
    scenario_id: str
    title: str
    description: str
    metadata: PackMetadata
    dimension: AssuranceDimension
    available_tools: tuple[str, ...]
    requirements: tuple[EvidenceRequirement, ...]
    tools: tuple[ToolSpec, ...]
    faults: tuple[FaultInjection, ...]

    @property
    def contract(self) -> EvidenceContract:
        """Return the evidence contract declared by the pack."""

        return EvidenceContract(
            scenario_id=self.scenario_id,
            requirements=self.requirements,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the strict public pack shape."""

        return {
            "pack_version": self.pack_version,
            "scenario_id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "metadata": self.metadata.to_dict(),
            "dimension": self.dimension.value,
            "available_tools": list(self.available_tools),
            "requirements": [
                requirement.to_dict() for requirement in self.requirements
            ],
            "tools": [
                {
                    "name": tool.name,
                    "result_status": tool.result_status,
                    "result_id": tool.result_id,
                    "side_effect_id": tool.side_effect_id,
                    "requires_authorization": tool.requires_authorization,
                    "output_flags": list(tool.output_flags),
                }
                for tool in self.tools
            ],
            "faults": [
                {
                    "fault_id": fault.fault_id,
                    "tool_name": fault.tool_name,
                    "mode": fault.mode.value,
                }
                for fault in self.faults
            ],
        }


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object.")
    return value


def _keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields.")


def _required_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string.")
    return value


def _string_list(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{context} must be a list of non-empty strings.")
    if len(value) != len(set(value)):
        raise ValueError(f"{context} must not contain duplicates.")
    return tuple(value)


def _parse_dimension(value: object) -> AssuranceDimension:
    try:
        return AssuranceDimension(_required_string(value, "dimension"))
    except ValueError as error:
        raise ValueError("dimension is not a supported assurance dimension.") from error


def _parse_metadata(value: object) -> PackMetadata:
    data = _object(value, "metadata")
    _keys(data, {"owner", "purpose", "data_class"}, "metadata")
    data_class = _required_string(data.get("data_class"), "metadata.data_class")
    if data_class != "synthetic":
        raise ValueError("metadata.data_class must be synthetic.")
    return PackMetadata(
        owner=_required_string(data.get("owner"), "metadata.owner"),
        purpose=_required_string(data.get("purpose"), "metadata.purpose"),
        data_class=data_class,
    )


def _parse_requirements(value: object) -> tuple[EvidenceRequirement, ...]:
    if not isinstance(value, list):
        raise ValueError("requirements must be a list.")
    requirements = []
    seen_ids: set[str] = set()
    for index, raw_requirement in enumerate(value):
        data = _object(raw_requirement, f"requirements[{index}]")
        _keys(
            data,
            {"requirement_id", "description", "evidence_type"},
            f"requirements[{index}]",
        )
        requirement_id = _required_string(
            data.get("requirement_id"),
            f"requirements[{index}].requirement_id",
        )
        if requirement_id in seen_ids:
            raise ValueError("requirements must not contain duplicate requirement_id values.")
        seen_ids.add(requirement_id)
        evidence_type = _required_string(
            data.get("evidence_type"),
            f"requirements[{index}].evidence_type",
        )
        if evidence_type not in SUPPORTED_EVIDENCE_TYPES:
            raise ValueError(
                f"requirements[{index}].evidence_type is not supported."
            )
        required_prefix = REQUIRED_ID_PREFIXES[evidence_type]
        if not requirement_id.startswith(required_prefix) or not requirement_id[
            len(required_prefix) :
        ]:
            raise ValueError(
                f"requirements[{index}].requirement_id must use the "
                f"{required_prefix} prefix for {evidence_type}."
            )
        requirements.append(
            EvidenceRequirement(
                requirement_id=requirement_id,
                description=_required_string(
                    data.get("description"),
                    f"requirements[{index}].description",
                ),
                evidence_type=evidence_type,
            )
        )
    return tuple(requirements)


def _parse_tools(value: object) -> tuple[ToolSpec, ...]:
    if not isinstance(value, list):
        raise ValueError("tools must be a list.")
    tools = []
    seen_names: set[str] = set()
    for index, raw_tool in enumerate(value):
        data = _object(raw_tool, f"tools[{index}]")
        _keys(
            data,
            {
                "name",
                "result_status",
                "result_id",
                "side_effect_id",
                "requires_authorization",
                "output_flags",
            },
            f"tools[{index}]",
        )
        name = _required_string(data.get("name"), f"tools[{index}].name")
        if name in seen_names:
            raise ValueError("tools must not contain duplicate name values.")
        seen_names.add(name)
        requires_authorization = data.get("requires_authorization")
        if not isinstance(requires_authorization, bool):
            raise ValueError(
                f"tools[{index}].requires_authorization must be a boolean."
            )
        side_effect_id = data.get("side_effect_id")
        if side_effect_id is not None and (
            not isinstance(side_effect_id, str) or not side_effect_id
        ):
            raise ValueError(f"tools[{index}].side_effect_id must be a string or null.")
        tools.append(
            ToolSpec(
                name=name,
                result_status=_required_string(
                    data.get("result_status"),
                    f"tools[{index}].result_status",
                ),
                result_id=_required_string(
                    data.get("result_id"),
                    f"tools[{index}].result_id",
                ),
                side_effect_id=side_effect_id,
                requires_authorization=requires_authorization,
                output_flags=_string_list(
                    data.get("output_flags"),
                    f"tools[{index}].output_flags",
                ),
            )
        )
    return tuple(tools)


def _parse_faults(
    value: object,
    tool_names: set[str],
) -> tuple[FaultInjection, ...]:
    if not isinstance(value, list):
        raise ValueError("faults must be a list.")
    faults = []
    seen_ids: set[str] = set()
    for index, raw_fault in enumerate(value):
        data = _object(raw_fault, f"faults[{index}]")
        _keys(data, {"fault_id", "tool_name", "mode"}, f"faults[{index}]")
        fault_id = _required_string(data.get("fault_id"), f"faults[{index}].fault_id")
        if fault_id in seen_ids:
            raise ValueError("faults must not contain duplicate fault_id values.")
        seen_ids.add(fault_id)
        tool_name = _required_string(
            data.get("tool_name"),
            f"faults[{index}].tool_name",
        )
        if tool_name not in tool_names:
            raise ValueError(f"faults[{index}].tool_name is not declared in tools.")
        try:
            mode = FaultMode(_required_string(data.get("mode"), f"faults[{index}].mode"))
        except ValueError as error:
            raise ValueError(f"faults[{index}].mode is not supported.") from error
        faults.append(
            FaultInjection(
                fault_id=fault_id,
                tool_name=tool_name,
                mode=mode,
            )
        )
    return tuple(faults)


def _parse_pack(value: object) -> ScenarioPack:
    data = _object(value, "pack")
    _keys(
        data,
        {
            "pack_version",
            "scenario_id",
            "title",
            "description",
            "metadata",
            "dimension",
            "available_tools",
            "requirements",
            "tools",
            "faults",
        },
        "pack",
    )
    if data.get("pack_version") != PACK_VERSION:
        raise ValueError("pack_version is not supported.")
    available_tools = _string_list(data.get("available_tools"), "available_tools")
    requirements = _parse_requirements(data.get("requirements"))
    tools = _parse_tools(data.get("tools"))
    tool_names = {tool.name for tool in tools}
    if set(available_tools) != tool_names:
        raise ValueError("available_tools must exactly match the declared tool names.")
    faults = _parse_faults(data.get("faults"), tool_names)
    return ScenarioPack(
        pack_version=PACK_VERSION,
        scenario_id=_required_string(data.get("scenario_id"), "scenario_id"),
        title=_required_string(data.get("title"), "title"),
        description=_required_string(data.get("description"), "description"),
        metadata=_parse_metadata(data.get("metadata")),
        dimension=_parse_dimension(data.get("dimension")),
        available_tools=available_tools,
        requirements=requirements,
        tools=tools,
        faults=faults,
    )


def decode_scenario_pack(value: object, *, source: str = "<memory>") -> PackResult:
    """Decode one pack value into a pack or structured refusal."""

    try:
        return PackResult(pack=_parse_pack(value))
    except ValueError as error:
        return PackResult(
            refusal=PackRefusal(
                error="invalid_scenario_pack",
                message=str(error),
                guidance="Correct the named pack field and validate it before running the harness.",
                source=source,
            )
        )


def load_scenario_pack(path: Path) -> PackResult:
    """Load and validate one JSON pack file."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PackResult(
            refusal=PackRefusal(
                error="unreadable_scenario_pack",
                message="The scenario pack could not be read as UTF-8 JSON.",
                guidance="Check the path and emit one JSON object with the documented schema.",
                source=str(path),
            )
        )
    return decode_scenario_pack(value, source=str(path))


def _builtin_pack_resources() -> tuple[resources.abc.Traversable, ...]:
    directory = resources.files("agent_reliability_lab").joinpath("scenario_packs")
    return tuple(
        sorted(
            (item for item in directory.iterdir() if item.name.endswith(".json")),
            key=lambda item: item.name,
        )
    )


def load_builtin_pack_results() -> tuple[PackResult, ...]:
    """Load all packaged scenario packs without executing their content."""

    results = []
    for resource in _builtin_pack_resources():
        try:
            value = json.loads(resource.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            results.append(
                PackResult(
                    refusal=PackRefusal(
                        error="unreadable_scenario_pack",
                        message="A built-in scenario pack could not be read as JSON.",
                        guidance="Repair the checked-in pack before running the harness.",
                        source=resource.name,
                    )
                )
            )
        else:
            results.append(decode_scenario_pack(value, source=resource.name))
    return _append_duplicate_refusal(tuple(results), source="built-in scenario packs")


def _append_duplicate_refusal(
    results: tuple[PackResult, ...],
    *,
    source: str,
) -> tuple[PackResult, ...]:
    """Add one refusal when valid packs reuse a scenario ID."""

    packs = [result.pack for result in results if result.pack is not None]
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for pack in packs:
        if pack.scenario_id in seen_ids:
            duplicate_ids.add(pack.scenario_id)
        seen_ids.add(pack.scenario_id)
    if not duplicate_ids:
        return results
    duplicate_list = ", ".join(sorted(duplicate_ids))
    return results + (
        PackResult(
            refusal=PackRefusal(
                error="duplicate_scenario_id",
                message=f"Scenario packs contain duplicate scenario IDs: {duplicate_list}.",
                guidance="Give each scenario pack a unique scenario_id before listing or running it.",
                source=source,
            )
        ),
    )


def load_builtin_packs() -> tuple[ScenarioPack, ...]:
    """Return valid built-in packs or fail closed for a developer artifact defect."""

    results = load_builtin_pack_results()
    refusals = [result.refusal for result in results if result.refusal is not None]
    if refusals:
        raise RuntimeError("A built-in scenario pack is invalid.")
    packs = tuple(result.pack for result in results if result.pack is not None)
    if len({pack.scenario_id for pack in packs}) != len(packs):
        raise RuntimeError("Built-in scenario packs contain duplicate scenario IDs.")
    return packs


def load_pack_directory(directory: Path) -> tuple[PackResult, ...]:
    """Load only explicitly named JSON files from one caller-supplied directory."""

    if not directory.is_dir():
        return (
            PackResult(
                refusal=PackRefusal(
                    error="pack_directory_not_found",
                    message="The supplied scenario-pack directory does not exist.",
                    guidance="Supply an existing directory containing JSON scenario packs.",
                    source=str(directory),
                )
            ),
        )
    paths = sorted(directory.glob("*.json"))
    if not paths:
        return (
            PackResult(
                refusal=PackRefusal(
                    error="empty_pack_directory",
                    message="The supplied scenario-pack directory contains no JSON packs.",
                    guidance="Add at least one JSON scenario pack before listing or running it.",
                    source=str(directory),
                )
            ),
        )
    return _append_duplicate_refusal(
        tuple(load_scenario_pack(path) for path in paths),
        source=str(directory),
    )


def build_environment_from_pack(pack: ScenarioPack) -> SimulatedToolEnvironment:
    """Build a simulator from validated pack values."""

    return SimulatedToolEnvironment(tools=pack.tools, faults=pack.faults)


def request_from_pack(pack: ScenarioPack) -> ScenarioRequest:
    """Build an adapter request directly from one validated pack."""

    return ScenarioRequest(
        scenario_id=pack.scenario_id,
        task_label=pack.title,
        available_tools=pack.available_tools,
        contract=pack.contract,
    )
