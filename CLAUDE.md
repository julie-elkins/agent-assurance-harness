# Agent Reliability Lab

## What this repository does

This repository tests whether a tool-using agent can support its claims with observable
evidence. An evidence contract is the minimum evidence required before a finding can pass.
The harness is offline and uses synthetic scenarios only.

## MCP server

The MCP server is a local, read-only tool surface for the same evidence contract. MCP
(Model Context Protocol) is the typed tool interface used by an AI client to call it.
Start it with:

```bash
uv run agent-reliability-mcp
```

The server exposes exactly three tools:

1. `list_scenario_packs` — call first when the scenario identifier is unknown.
2. `evaluate_agent_trace` — submit one identifier-only synthetic trace for evaluation.
3. `run_reference_comparison` — run the built-in naive and guarded reference agents.

Read `diagnostics`, `refusals`, and `what_it_does_not_show` before reporting a result.
An empty list is not a pass: it can mean that nothing was checked.

## Operating boundaries

- Do not add live provider calls, credentials, customer data, exam content, or network
  access to the MCP server.
- Do not add arbitrary subprocess or shell execution to an MCP tool.
- Do not accept raw tool arguments or raw tool-result payloads in submitted traces.
- Keep stdout reserved for MCP protocol messages; diagnostics belong on stderr through the
  SDK's logging path.
- Keep output models typed and explicit. Optional output fields must remain nullable.

## Verification

From a fresh checkout:

```bash
uv sync --extra dev
uv run pytest
uv run agent-reliability --list-packs --json
```

The stdio client test in `tests/unit/test_mcp_server.py` is the required transport check.
In-process calls alone are insufficient because they cannot verify initialization metadata,
transport separation, or the served output schema.
