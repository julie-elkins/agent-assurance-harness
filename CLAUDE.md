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

The Phase 12 candidate demonstration is reproducible locally:

```bash
uv run python examples/candidate_replay.py > /tmp/candidate-replay.json
uv run agent-reliability \
  --compare-replay examples/traces/guarded.json /tmp/candidate-replay.json \
  --json \
  --fail-on-findings
```

Phase 13 exercises mocked OpenAI-shaped and Anthropic-shaped adapters through the same
recorder and evaluator path:

```bash
uv run agent-reliability \
  --mock-provider all \
  --json \
  --mutations \
  --fail-on-findings
```

These adapters are credential-free and offline. They validate only the credential
environment-variable name and synthetic usage ceilings; they do not read credentials or
make network calls. Live provider support requires a separate security and delivery review.

Phase 14 provides a local-only live boundary for one built-in synthetic scenario:

```bash
uv run agent-reliability \
  --live-provider openai \
  --scenario-id unauthorized-side-effect \
  --model MODEL_ID \
  --allow-network \
  --max-requests 1 \
  --max-output-tokens 256 \
  --max-elapsed-seconds 30 \
  --max-estimated-cost-usd 0.05 \
  --estimated-cost-usd-per-request 0.01 \
  --json \
  --fail-on-findings
```

The live command reads only the fixed provider credential environment variable and sends
only built-in synthetic identifiers. It is not run in CI, does not retry, and does not
store raw provider requests, responses, or model text.

Phase 15 adds production-readiness checks without enabling live execution in CI:

```bash
uv run python tools/check_repository_boundaries.py
uv run python tools/audit_dependencies.py
uv run pytest
```

The boundary check scans tracked files for high-signal credential patterns and checks that
the blocking workflow has read-only permissions and no provider credentials or live flag.
It is a guard, not proof that every possible secret was found. Synthetic provider
contract fixtures exercise the reviewed OpenAI and Anthropic response subsets offline.
See `SECURITY.md` before using the live boundary with anything other than built-in
synthetic input.

Phase 16 verifies the built release artifact in a clean environment:

```bash
uv run python tools/release_check.py \
  --sbom-output /tmp/agent-reliability-runtime-sbom.json \
  --manifest-output /tmp/agent-reliability-release-manifest.json
```

The manifest contains package, commit, scenario-pack, artifact, and assurance-output
hashes plus a dirty-checkout indicator; it does not contain traces, prompts, credentials,
or model text.

Phase 17 generates the public synthetic benchmark:

```bash
uv run python tools/benchmark_report.py \
  --output /tmp/agent-reliability-benchmark.json \
  --fail-on-findings
```

The report compares the reference and mocked adapters using status counts and hashes only.
It is a deterministic assurance benchmark, not a live-model quality ranking.

Phase 18 checks an external adapter against the public conformance contract:

```bash
uv run python tools/conformance_report.py \
  --agent-id external \
  --adapter-command uv \
  --adapter-command run \
  --adapter-command python \
  --adapter-command examples/guarded_adapter.py \
  --output /tmp/agent-reliability-conformance.json \
  --fail-on-findings
```

The conformance report contains counts and statuses only; it does not expose the adapter
command, findings, traces, prompts, credentials, or provider output.

Phase 19 hardens external adapter execution with process-group termination, bounded
diagnostics, optional working-directory control, and best-effort Unix CPU/address-space
limits. This is not a network sandbox; use an OS or container boundary for hostile code.

For integrations, use `TraceRecorder` rather than a provider SDK. It emits the existing
identifier-only `AdapterRun` protocol, pairs tool calls with results, and returns
structured refusals for raw arguments, raw result payloads, and free-form claims or
answers.

The executable integration reference is `examples/recorder_adapter.py`. CI generates
and replays its output, then runs it through the subprocess JSONL adapter boundary.

`--otlp-file` imports only the strict local OTLP/JSON subset represented by
`examples/traces/otel-guarded.json`. Known content-bearing GenAI attributes are refused;
the importer does not run a collector, accept network input, or store raw span content.
