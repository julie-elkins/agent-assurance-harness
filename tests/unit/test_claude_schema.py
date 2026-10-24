from agent_reliability_lab.claude_schema import (
    CLAUDE_SCHEMA_VERSION,
    claude_output_schema,
    claude_structured_output_schema,
    synthetic_tool_definitions,
    validate_claude_output,
)


def test_schema_is_versioned_and_tools_are_zero_argument():
    assert claude_output_schema()["schema_version"] == CLAUDE_SCHEMA_VERSION
    tools = synthetic_tool_definitions(("lookup_policy",))

    assert tools[0]["name"] == "lookup_policy"
    assert tools[0]["strict"] is True
    assert tools[0]["input_schema"]["properties"] == {}
    assert tools[0]["input_schema"]["additionalProperties"] is False


def test_provider_structured_schema_uses_finite_kinds_and_closed_objects():
    schema = claude_structured_output_schema()
    event = schema["properties"]["content"]["items"]

    assert event["properties"]["kind"]["enum"]
    assert event["additionalProperties"] is False
    assert schema["additionalProperties"] is False
    assert "minimum" not in schema["properties"]["workflow"]["properties"]["retry_count"]


def test_schema_accepts_final_classification():
    refusal = validate_claude_output(
        {
            "content": [
                {
                    "type": "reliability",
                    "kind": "claim",
                    "id": "claim:provider_safe",
                }
            ]
        },
        available_tools=("lookup_policy",),
    )

    assert refusal is None


def test_schema_refuses_non_empty_tool_arguments():
    refusal = validate_claude_output(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "lookup_policy",
                    "id": "call-001",
                    "input": {"record_id": "synthetic-policy-404"},
                }
            ]
        },
        available_tools=("lookup_policy",),
    )

    assert refusal is not None
    assert refusal.error == "claude_schema_tool_use_arguments_invalid"


def test_schema_requires_workflow_fields():
    refusal = validate_claude_output(
        {
            "content": [
                {
                    "type": "reliability",
                    "kind": "abstention",
                }
            ],
            "workflow": {"workflow_id": "workflow-001"},
        },
        available_tools=("lookup_policy",),
    )

    assert refusal is not None
    assert refusal.error == "claude_schema_workflow_fields_invalid"
