import anyio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent_reliability_lab.mcp_server import server


def test_tool_surface_is_narrow_typed_and_read_only():
    async def inspect_surface():
        return await server.list_tools()

    tools = anyio.run(inspect_surface)
    names = [tool.name for tool in tools]

    assert names == [
        "list_scenario_packs",
        "evaluate_agent_trace",
        "run_reference_comparison",
    ]
    assert all(
        not left.startswith(right)
        for left in names
        for right in names
        if left != right
    )
    assert all(tool.annotations.read_only_hint is True for tool in tools)
    assert all(tool.annotations.open_world_hint is False for tool in tools)
    assert all(tool.output_schema for tool in tools)
    assert all(tool.description for tool in tools)


def test_in_process_tools_return_structured_results():
    async def call_tools():
        packs = await server.call_tool("list_scenario_packs", {})
        comparison = await server.call_tool(
            "run_reference_comparison",
            {"include_mutations": True},
        )
        evaluated = await server.call_tool(
            "evaluate_agent_trace",
            {
                "scenario_id": "tool-misuse",
                "trace": {
                    "scenario_id": "tool-misuse",
                    "agent_id": "synthetic-agent",
                    "tool_calls": [],
                    "abstained": True,
                },
            },
        )
        return packs, comparison, evaluated

    packs, comparison, evaluated = anyio.run(call_tools)

    assert packs.is_error is False
    assert len(packs.structured_content["packs"]) == 5
    assert comparison.is_error is False
    assert comparison.structured_content["scenario_count"] == 5
    assert all(item["caught"] for item in comparison.structured_content["mutation_tests"])
    assert evaluated.is_error is False
    assert evaluated.structured_content["finding"]["status"] == "failed"


def test_unknown_scenario_is_a_structured_refusal():
    async def call_tool():
        return await server.call_tool(
            "evaluate_agent_trace",
            {
                "scenario_id": "not-a-pack",
                "trace": {
                    "scenario_id": "not-a-pack",
                    "agent_id": "synthetic-agent",
                    "abstained": True,
                },
            },
        )

    result = anyio.run(call_tool)

    assert result.is_error is False
    assert result.structured_content["finding"] is None
    assert result.structured_content["refusal"]["error"] == "unknown_scenario"


def test_stdio_client_sees_initialization_surface_and_tool_result():
    repository = Path(__file__).parents[2]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent_reliability_lab.mcp_server"],
        cwd=repository,
    )

    async def run_client():
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialization = await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("list_scenario_packs", {})
                return initialization, tools, result

    initialization, tools, result = anyio.run(run_client)

    assert initialization.server_info.name == "agent-reliability-lab"
    assert initialization.server_info.version == "0.4.0"
    assert "list_scenario_packs" in initialization.instructions
    assert [tool.name for tool in tools.tools] == [
        "list_scenario_packs",
        "evaluate_agent_trace",
        "run_reference_comparison",
    ]
    assert result.is_error is False
    assert len(result.structured_content["packs"]) == 5
