import json

from agent_reliability_lab.models import AssuranceDimension
from agent_reliability_lab.packs import (
    build_environment_from_pack,
    decode_scenario_pack,
    load_builtin_packs,
    load_pack_directory,
    request_from_pack,
)
from agent_reliability_lab.pack_provenance import (
    pack_manifest,
    pack_set_sha256,
    pack_sha256,
)
from agent_reliability_lab.scenarios import scenarios


def test_builtin_packs_match_reference_scenarios():
    packs = load_builtin_packs()
    reference = {scenario.scenario_id: scenario for scenario in scenarios()}

    assert {pack.scenario_id for pack in packs} == set(reference)
    for pack in packs:
        scenario = reference[pack.scenario_id]
        assert pack.contract == scenario.contract
        assert pack.dimension is scenario.dimension
        assert pack.available_tools == scenario.available_tools


def test_pack_builds_simulator_and_adapter_request():
    pack = next(
        pack
        for pack in load_builtin_packs()
        if pack.scenario_id == "misleading-tool-output"
    )

    environment = build_environment_from_pack(pack)
    observation = environment.invoke("lookup_catalog")
    request = request_from_pack(pack)

    assert observation.output_flags == ("instruction_like",)
    assert request.contract == pack.contract
    assert request.available_tools == pack.available_tools


def test_builtin_packs_declare_synthetic_provenance():
    for pack in load_builtin_packs():
        assert pack.metadata.data_class == "synthetic"
        assert pack.metadata.owner
        assert pack.metadata.purpose


def test_pack_fingerprint_is_stable_and_changes_with_definition():
    pack = load_builtin_packs()[0]
    first = pack_sha256(pack)
    second = pack_sha256(pack)

    assert first == second
    assert len(first) == 64
    assert pack_manifest(pack).pack_sha256 == first

    changed = dict(pack.to_dict())
    changed["description"] = "A changed synthetic description."
    decoded = decode_scenario_pack(changed, source="test-pack")

    assert decoded.pack is not None
    assert pack_sha256(decoded.pack) != first


def test_pack_set_fingerprint_is_stable_and_order_independent():
    packs = load_builtin_packs()
    first = pack_set_sha256(packs)
    second = pack_set_sha256(tuple(reversed(packs)))

    assert first == second
    assert len(first) == 64


def test_pack_rejects_unknown_and_payload_fields():
    value = load_builtin_packs()[0].to_dict()
    value["payload"] = "must not be accepted"

    result = decode_scenario_pack(value, source="test-pack")

    assert result.pack is None
    assert result.refusal is not None
    assert result.refusal.error == "invalid_scenario_pack"


def test_pack_rejects_unsupported_requirement_type():
    value = load_builtin_packs()[0].to_dict()
    value["requirements"][0]["evidence_type"] = "executable_predicate"

    result = decode_scenario_pack(value, source="test-pack")

    assert result.refusal is not None
    assert "not supported" in result.refusal.message


def test_pack_rejects_partial_source_freshness_requirement():
    value = next(
        pack
        for pack in load_builtin_packs()
        if pack.scenario_id == "evidence-freshness-source"
    ).to_dict()
    value["requirements"][0].pop("max_age_seconds")

    result = decode_scenario_pack(value, source="test-pack")

    assert result.pack is None
    assert result.refusal is not None
    assert "together" in result.refusal.message


def test_pack_rejects_non_synthetic_metadata():
    value = load_builtin_packs()[0].to_dict()
    value["metadata"]["data_class"] = "private"

    result = decode_scenario_pack(value, source="test-pack")

    assert result.pack is None
    assert result.refusal is not None
    assert "synthetic" in result.refusal.message


def test_pack_directory_lists_new_valid_pack_without_python_change(tmp_path):
    value = load_builtin_packs()[0].to_dict()
    value["scenario_id"] = "new-standard-pack"
    value["title"] = "New standard pack"
    path = tmp_path / "new-standard-pack.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    results = load_pack_directory(tmp_path)

    assert len(results) == 1
    assert results[0].pack is not None
    assert results[0].pack.scenario_id == "new-standard-pack"


def test_empty_pack_directory_is_a_refusal(tmp_path):
    results = load_pack_directory(tmp_path)

    assert len(results) == 1
    assert results[0].refusal is not None
    assert results[0].refusal.error == "empty_pack_directory"


def test_pack_directory_rejects_duplicate_scenario_ids(tmp_path):
    value = load_builtin_packs()[0].to_dict()
    (tmp_path / "first.json").write_text(json.dumps(value), encoding="utf-8")
    (tmp_path / "second.json").write_text(json.dumps(value), encoding="utf-8")

    results = load_pack_directory(tmp_path)

    assert [result.pack.scenario_id for result in results if result.pack is not None] == [
        value["scenario_id"],
        value["scenario_id"],
    ]
    refusals = [result.refusal for result in results if result.refusal is not None]
    assert len(refusals) == 1
    assert refusals[0].error == "duplicate_scenario_id"
