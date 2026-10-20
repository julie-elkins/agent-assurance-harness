from agent_reliability_lab.conformance import run_custom_pack_conformance
from agent_reliability_lab.packs import decode_scenario_pack
from agent_reliability_lab.recorder import TraceRecorder


class CustomPackAdapter:
    agent_id = "custom-test"

    def run(self, request, environment):
        del environment
        recorder = TraceRecorder(
            scenario_id=request.scenario_id,
            agent_id=self.agent_id,
        )
        recorder.record_tool_call("lookup_record")
        recorder.record_tool_result(
            "lookup_record",
            "not_found",
            result_id="custom-result-001",
        )
        recorder.record_abstention()
        return recorder.finish()


def _pack_value():
    return {
        "pack_version": 1,
        "scenario_id": "custom-pack",
        "title": "Custom pack",
        "description": "Synthetic custom pack.",
        "dimension": "evidence_completeness",
        "available_tools": ["lookup_record"],
        "requirements": [
            {
                "requirement_id": "tool:lookup_record",
                "description": "Observe the lookup.",
                "evidence_type": "tool_call",
            },
            {
                "requirement_id": "abstain:when-evidence-insufficient",
                "description": "Abstain when evidence is insufficient.",
                "evidence_type": "agent_behaviour",
            },
        ],
        "tools": [
            {
                "name": "lookup_record",
                "result_status": "not_found",
                "result_id": "custom-result-001",
                "side_effect_id": None,
                "requires_authorization": False,
                "output_flags": [],
            }
        ],
        "faults": [],
    }


def test_custom_pack_runs_through_declarative_conformance():
    result = decode_scenario_pack(_pack_value(), source="test-custom-pack")
    assert result.pack is not None

    report = run_custom_pack_conformance(CustomPackAdapter(), (result.pack,))

    assert report.passed
    assert report.to_dict()["pack_ids"] == ["custom-pack"]
    assert report.to_dict()["refusal_count"] == 0


def test_custom_pack_rejects_requirement_prefix_mismatch():
    value = _pack_value()
    value["requirements"][0]["requirement_id"] = "abstain:wrong-type"

    result = decode_scenario_pack(value, source="test-custom-pack")

    assert result.pack is None
    assert result.refusal is not None
    assert "prefix" in result.refusal.message
