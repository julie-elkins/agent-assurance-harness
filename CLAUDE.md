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
4. `run_gated_scenario` — run a naive or guarded profile through the before-action gate.

Read `diagnostics`, `refusals`, and `what_it_does_not_show` before reporting a result.
An empty list is not a pass: it can mean that nothing was checked.

The gate is the prevention path. A naive profile should be blocked when required evidence
is absent. A guarded profile should proceed only after the evidence requirement is
satisfied. For `unauthorized-side-effect`, verify that a blocked naive run has no tool
events and no side effect; that absence proves the gate stopped the action before the
synthetic environment.

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

## Replay and CI

The checked-in replay fixture is `examples/traces/guarded.json`. A replay file is a
versioned collection of identifier-only adapter responses covering exactly all five
scenario packs. Run it with:

```bash
uv run agent-reliability \
  --replay-file examples/traces/guarded.json \
  --json \
  --fail-on-findings
```

Do not add prompts, hidden reasoning, raw tool arguments, raw tool results, credentials,
or live traces to a replay file. The GitHub Actions workflow is the delivery gate for
tests, pack validation, replay, and the guarded external adapter.

To compare a candidate harness with the approved baseline, add an identifier-only
`harness_change` manifest naming the change ID and changed components, then run:

```bash
uv run agent-reliability \
  --compare-replay examples/traces/guarded.json ./candidate.json \
  --json \
  --fail-on-findings
```

The comparison blocks new safety or evidence failures, refusals, and lost evidence. It
reports task-outcome regressions without treating them as release blockers. The manifest
must never contain prompts, memory text, raw tool payloads, or provider output.

For integrations, use `TraceRecorder` rather than a provider SDK. It emits the existing
identifier-only `AdapterRun` protocol, pairs tool calls with results, and returns
structured refusals for raw arguments, raw result payloads, and free-form claims or
answers.

The executable integration reference is `examples/recorder_adapter.py`. CI generates
and replays its output, then runs it through the subprocess JSONL adapter boundary.

`--otlp-file` imports only the strict local OTLP/JSON subset represented by
`examples/traces/otel-guarded.json`. Known content-bearing GenAI attributes are refused;
the importer does not run a collector, accept network input, or store raw span content.
