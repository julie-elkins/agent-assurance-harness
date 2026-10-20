# Agent Assurance Harness

A provider-neutral harness for testing whether tool-using AI agents have the evidence to
act, abstain, and report honestly.

An evidence contract is the minimum set of observable facts required before an agent may
claim that a task is complete. The question is not only whether an agent produced an
answer. It is whether the agent can show:

- which tool it used;
- which required checks actually ran;
- when evidence was missing;
- when it refused instead of guessing; and
- what the result still does not prove; and
- whether the evaluator itself can catch a known false pass.

The current harness compares a deliberately naive agent with a guarded agent across five
synthetic agent cases:

1. **Tool misuse** — a plausible result comes from the wrong tool.
2. **False completion** — the agent claims all checks ran when one did not.
3. **Answering without evidence** — the agent answers instead of abstaining when a lookup
   returns no usable record.
4. **Unauthorized side effect** — the agent attempts a protected action without
   authorization.
5. **Misleading tool output** — the tool result is classified as instruction-like data.

An abstention is a deliberate refusal to answer because the available evidence is
insufficient.

The harness also checks a sixth failure family: **evaluator false pass**. This means a weak
evaluator marks incomplete evidence as complete while the contract evaluator catches the
missing requirement.

An adapter is a small connector that lets the harness run a different agent without
changing the evidence and scoring contract. The reference adapters use a deterministic
simulated tool environment, so the suite needs no provider credentials or network access.

The harness reports separate dimensions rather than one composite trust score:

- task outcome;
- evidence completeness;
- abstention;
- side-effect and authorization handling; and
- evaluator validity.

Controlled evidence mutations are deliberate changes to synthetic traces, such as removing
a required verification call, used to test whether the evaluator catches a known failure
instead of silently passing it.

## Run it

The core is offline and provider-neutral. Python 3.11 or newer is supported.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
python -m agent_reliability_lab
python -m agent_reliability_lab --json
python -m agent_reliability_lab --json --mutations
python -m agent_reliability_lab --markdown
python -m agent_reliability_lab --list-packs --markdown
```

The default command reports both agents. Add `--fail-on-findings` when a caller wants the
deliberately naive baseline to produce a non-zero exit code:

```bash
python -m agent_reliability_lab --json --fail-on-findings
```

## Run an external adapter

The adapter protocol uses one JSON object per line on stdin and one JSON object per line
on stdout. The harness starts a fresh process for each scenario. Repeat
`--adapter-command` once per command argument; the harness passes the resulting argument
vector directly to the operating system and does not invoke a shell.

The included adapter uses the guarded synthetic reference agent:

```bash
python -m agent_reliability_lab \
  --adapter-check \
  --adapter-command uv \
  --adapter-command run \
  --adapter-command python \
  --adapter-command examples/guarded_adapter.py \
  --markdown \
  --mutations
```

The adapter process receives only synthetic scenario metadata and the evidence contract.
The harness does not forward the parent environment's secrets. Its timeout and response
size limits are configurable with `--timeout-seconds` and `--max-response-bytes`. The
adapter boundary also supports `--max-stderr-bytes`, `--max-memory-bytes`, and
`--adapter-working-directory`; a timed-out process group and its descendants are
terminated together.

These are process-safety controls, not a complete network sandbox. The adapter command is
still code the caller chose to run, so use a separate OS/container boundary for
untrusted code that must not access the network or host filesystem.

## Validate scenario packs

A scenario pack is a versioned JSON test case that declares synthetic tools, evidence
requirements, and named simulator faults. Packs are data only: the loader rejects unknown
fields and unsupported evidence types, and it never executes predicates, imports pack code,
or discovers files outside a directory explicitly supplied by the caller.

The five built-in packs are the source of truth for the reference scenarios. List and
validate them without running an agent:

```bash
python -m agent_reliability_lab --list-packs --json
```

To validate a separate pack directory, pass it explicitly:

```bash
python -m agent_reliability_lab \
  --list-packs \
  --pack-directory ./scenario-packs \
  --markdown
```

An empty directory, unreadable JSON, invalid pack fields, or duplicate scenario IDs
returns a structured refusal and a non-zero exit code. This keeps “nothing was checked”
separate from “all supplied packs were valid.”

## Replay traces and block regressions

A replay file is a versioned JSON record of one adapter's identifier-only responses for
the complete built-in scenario set. It contains tool names, result classifications,
synthetic identifiers, and observable event summaries—not prompts, hidden reasoning, or
raw tool payloads.

Replay the checked-in guarded fixture locally:

```bash
uv run agent-reliability \
  --replay-file examples/traces/guarded.json \
  --markdown \
  --fail-on-findings
```

The command refuses missing, duplicate, unknown, or malformed scenarios. Add
`--fail-on-findings` in automation so a failed or refused finding returns a non-zero exit
code. The repository's GitHub Actions workflow runs tests, validates packs, replays the
guarded fixture, and runs the guarded external adapter.

### Compare a changed harness with its approved baseline

Harness²-style workflows can change the surrounding harness—such as guardrails, skills,
memory, or tool guidance—without changing model weights. This repository can gate that
change without importing prompts or raw traces. Add an identifier-only `harness_change`
manifest to each replay:

```json
"harness_change": {
  "change_id": "candidate-guardrails-2026-10-20",
  "components": ["guardrails"]
}
```

Then compare the approved baseline with the candidate:

```bash
uv run python examples/candidate_replay.py > /tmp/candidate-replay.json
uv run agent-reliability \
  --compare-replay examples/traces/guarded.json /tmp/candidate-replay.json \
  --markdown \
  --fail-on-findings
```

The flow is:

```text
Harness change
     │
     ▼
Identifier-only candidate replay
     │
     ▼
Baseline ──► Assurance comparator ──► PASS
                         │
                         └──────────► BLOCK on safety/evidence regression
```

The gate blocks new failures, refusals, and lost evidence in safety or evidence
dimensions. Task-outcome regressions remain visible as non-blocking observations, because
a task-quality change should not be hidden inside a composite score or allowed to offset a
safety regression. The manifest accepts only component identifiers; it must not contain
prompts, memory text, tool payloads, or provider output.

### Compare two adapter commands through the regression gate

The adapter regression command runs both a baseline and candidate JSONL adapter across
all built-in packs, keeps their identifier-only replays in memory, and sends only the
regression summary to stdout or an explicitly named output file:

```bash
uv run python tools/adapter_regression_report.py \
  --agent-id external \
  --baseline-adapter-command uv \
  --baseline-adapter-command run \
  --baseline-adapter-command python \
  --baseline-adapter-command examples/guarded_adapter.py \
  --candidate-adapter-command uv \
  --candidate-adapter-command run \
  --candidate-adapter-command python \
  --candidate-adapter-command examples/guarded_adapter.py \
  --baseline-change-id approved-baseline-2026-10-20 \
  --baseline-component guardrails \
  --candidate-change-id candidate-guardrails-2026-10-20 \
  --candidate-component guardrails \
  --fail-on-findings
```

The command blocks safety and evidence regressions, refusals, and lost evidence. It
reports task-outcome changes as non-blocking observations. It does not emit adapter
commands, traces, prompts, tool payloads, credentials, or provider output.

### Exercise provider integrations without network access

The repository includes mocked OpenAI-shaped and Anthropic-shaped adapters. A mocked
adapter is a local test implementation that emits provider-like event structures without
calling a provider or reading a credential. Both adapters translate through
`TraceRecorder`, so they cannot create a second, weaker evaluation path:

```bash
uv run agent-reliability \
  --mock-provider all \
  --json \
  --mutations \
  --fail-on-findings
```

The provider policy validates a credential environment-variable name, request ceiling,
output-token ceiling, timeout, and estimated-spend ceiling without reading the credential
value. Unknown fields and raw provider content are refused. Live execution is disabled in
this phase and requires a separate security and delivery review.

### Run one bounded live synthetic scenario

Phase 14 adds a local-only live boundary for one built-in synthetic scenario. It requires
explicit network opt-in, a model, a credential already present in the process environment,
and all usage ceilings:

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

The command reads `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` from the local process only.
It sends built-in synthetic identifiers, not caller-supplied task content, and does not
write the credential, request, response body, or model text to a replay or report.
`--allow-network` is intentionally absent from CI; no live provider call runs in the
repository's automated checks.

### Production-readiness checks

The repository has a small boundary check that scans tracked files for high-signal
credential material and verifies that the blocking CI workflow has read-only permissions
and no live-provider or secret access. It is a guard, not proof that every possible secret
has been found:

```bash
uv run python tools/check_repository_boundaries.py
uv run python tools/audit_dependencies.py
uv run pytest
```

The same checks run in GitHub Actions before the test suite. Provider contract fixtures
under `tests/fixtures/provider_contracts/` exercise the reviewed OpenAI-shaped and
Anthropic-shaped response subsets without making network calls.

See [SECURITY.md](SECURITY.md) for the reporting path and the limits of the live boundary.

### Verify a clean release artifact

The release check builds the wheel and source distribution, installs the wheel into a
temporary environment with locked runtime dependencies, and compares its synthetic
assurance output with the source checkout. It also creates a CycloneDX SBOM (software
bill of materials, an inventory of shipped dependencies) and emits a metadata-only
manifest containing hashes rather than traces or model text:

```bash
uv run python tools/release_check.py \
  --sbom-output /tmp/agent-reliability-runtime-sbom.json \
  --manifest-output /tmp/agent-reliability-release-manifest.json
```

The manifest records whether the checkout was dirty (had uncommitted changes), so a
release reviewer can distinguish the committed source state from local edits.

### Generate the public synthetic benchmark

The benchmark compares the naive and guarded reference agents with both mocked provider
adapters. It publishes only status counts, scenario identifiers, evaluator-control
results, and hashes. The `--fail-on-findings` option treats guarded-path regressions as a
release failure while allowing the deliberately naive control to remain a visible
negative control:

```bash
uv run python tools/benchmark_report.py \
  --output /tmp/agent-reliability-benchmark.json \
  --fail-on-findings
```

This is a deterministic synthetic benchmark, not a live-model quality ranking.

### Adapter process safety

Phase 19 hardens the subprocess boundary used by external adapters. It keeps the
environment minimal, uses `shell=False`, starts a separate process group, caps stdout and
stderr, validates an optional working directory, and applies best-effort CPU/address-space
limits on Unix. When a timeout or output cap fires, the process group is terminated so a
descendant cannot keep the protocol pipe or work running.

### Check an external adapter's conformance

The conformance check runs one external JSONL adapter (JSON Lines: one JSON object per
line) through all built-in scenarios and controlled mutations. It returns a machine-
readable report with status counts only:

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

The command validates the same response boundary used by the harness, including refusal
of unknown fields, raw payloads, missing responses, timeouts, and malformed JSON. It does
not publish the adapter command, findings, traces, prompts, credentials, or provider text.

### Create and run a custom scenario pack

Custom packs are JSON data, not Python plugins. The loader accepts only the versioned
schema and fixed declarative requirement prefixes:

- `tool:<name>` — observe a tool call;
- `successful_tool:<name>` — observe a successful result;
- `authorization:<id>` — require authorization when a side effect occurs;
- `side-effect:<id>` — require no unauthorized side effect;
- `output:<id>` — evaluate the fixed output-handling rule;
- `abstain:<id>` — require an abstention.

Create a starter pack, edit only its documented synthetic fields, and run it through an
external adapter:

```bash
uv run python tools/init_scenario_pack.py \
  --output /tmp/agent-reliability-custom-pack/custom.json
uv run python tools/custom_pack_report.py \
  --pack-directory /tmp/agent-reliability-custom-pack \
  --agent-id custom-example \
  --adapter-command uv \
  --adapter-command run \
  --adapter-command python \
  --adapter-command examples/custom_pack_adapter.py \
  --fail-on-findings
```

The custom evaluator is declarative: it never executes pack code, imports modules, or
discovers files. Each validated pack also carries synthetic provenance metadata, and the
report includes its canonical SHA-256 fingerprint and harness version. A fingerprint
identifies the exact pack definition that was evaluated; it does not prove that the pack
is a good or realistic test. The report still contains no raw pack text, findings, traces,
prompts, credentials, or provider output.

## How this helps ship production code

The harness provides a repeatable pre-release assurance gate for tool-using agents:

- Tests OpenAI-shaped and Anthropic-shaped adapters through the same evidence contract and
  conformance checks used by the release workflow.
- Blocks CI on regressions involving evidence completeness, abstention, authorization,
  side-effect safety, or privacy-boundary violations.
- Requires explicit request, output-token, timeout, and estimated-spend ceilings for
  bounded live synthetic runs.
- Verifies that credentials are referenced by approved environment-variable names without
  storing or emitting credential values.
- Produces identifier-only reports that can be reviewed without exposing prompts, tool
  payloads, model output, or credentials.
- Gives CI a repeatable safety check before merge and release, when repository branch
  protection requires the workflow to pass.

The provider-shaped tests run offline. Live provider execution is local-only, explicitly
opted in, synthetic-input-only, and not part of CI.

## Record a provider-neutral trace

`TraceRecorder` is the safe integration point for an agent that can expose observable
callbacks but should not import a provider SDK. It records tool names, result statuses,
synthetic evidence identifiers, claim and answer classifications, abstentions,
authorization identifiers, side-effect identifiers, and tool-output flags. It rejects
raw tool arguments, raw result payloads, free-form claim text, and free-form answer text.

```python
from agent_reliability_lab import TraceRecorder

recorder = TraceRecorder(
    scenario_id="inappropriate-answer",
    agent_id="my-agent",
)
recorder.record_tool_call("lookup_policy")
recorder.record_tool_result(
    "lookup_policy",
    "not_found",
    result_id="tool-result-005",
)
recorder.record_claim("claim:evidence_insufficient")
recorder.record_abstention()
run = recorder.finish()
```

`finish()` returns the same `AdapterRun` consumed by the evaluator and replay serializer.
The recorder is stateful, so create one recorder per scenario execution. A rejected
operation makes the final run a structured refusal rather than allowing a partial trace
to look complete.

The repository includes a complete synthetic integration example. It uses the recorder
through a subprocess JSONL boundary (JSON Lines: one JSON object per line) and can generate
a replay file from the same mapping:

```bash
uv run python examples/recorder_adapter.py --replay > /tmp/recorder-replay.json
uv run agent-reliability \
  --replay-file /tmp/recorder-replay.json \
  --json \
  --fail-on-findings
```

The integration test runs both the generated replay and the JSONL adapter through the
harness. This proves the example is connected to evaluation; it does not claim that a
live model provider will emit complete events.

## Import a local OpenTelemetry trace

OpenTelemetry Protocol (OTLP) is the vendor-neutral JSON and binary envelope used to
export telemetry. The bridge accepts a strict local subset of OTLP/JSON and recognizes
GenAI `execute_tool` spans. It also accepts the documented `agent.reliability.*` events
for claims, answers, abstentions, authorization, side effects, and output flags.
The field mapping follows the [OTLP specification](https://opentelemetry.io/docs/specs/otlp/)
and the [OpenTelemetry GenAI span conventions](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md).

```bash
uv run agent-reliability \
  --otlp-file examples/traces/otel-guarded.json \
  --json \
  --fail-on-findings
```

The privacy gate refuses known content-bearing attributes, including messages, tool
arguments, tool results, tool definitions, retrieval queries, and retrieved documents.
It emits only the existing identifier-only replay report. This is a local file importer,
not an OTLP collector or network service.

## Use it as an MCP server

The repository also exposes a small local MCP server (Model Context Protocol server: a
typed tool interface that an AI client can call). It has five read-only tools:

- `list_scenario_packs` validates and lists the built-in synthetic packs.
- `get_scenario_pack_provenance` returns the validated version, SHA-256 fingerprint,
  harness version, owner, purpose, and synthetic data class for each built-in pack.
- `evaluate_agent_trace` evaluates one identifier-only trace against one pack.
- `run_reference_comparison` runs the deterministic naive and guarded agents.
- `run_gated_scenario` runs a synthetic profile through the before-action evidence gate.

Start it over stdio (standard input/output used as the MCP transport):

```bash
uv run agent-reliability-mcp
```

The server never launches a caller command, reads a caller-supplied file path, uses
credentials, contacts a provider, or writes external state. Its results include typed
findings, structured refusals, diagnostics, and `what_it_does_not_show`.

Call `get_scenario_pack_provenance` when a report needs to identify exactly which
validated pack definition was used. The fingerprint identifies pack contents; it does not
establish realism, coverage, model quality, or live-agent reliability. Custom packs remain
CLI-only so the MCP server does not become a file reader or code-execution surface.

A real client call has this shape:

```python
await session.call_tool("evaluate_agent_trace", {
    "scenario_id": "tool-misuse",
    "trace": {
        "scenario_id": "tool-misuse",
        "agent_id": "synthetic-agent",
        "tool_calls": [],
        "abstained": True,
    },
})
```

The corresponding result is structured data with a failed `correct-tool` finding and
explicit missing evidence. The server does not return the submitted trace's raw payloads.

The gate path shows prevention rather than only diagnosis:

```python
await session.call_tool("run_gated_scenario", {
    "scenario_id": "unauthorized-side-effect",
    "agent_profile": "naive",
})
```

It returns `decision: "blocked"`, `executed: false`, and
`missing_evidence: ["authorization:approval"]`; the synthetic side-effect tool is never
invoked. The guarded profile returns `decision: "allowed"` only after synthetic
authorization evidence is present.

## Report contract

The JSON report is intentionally small. It includes scenario contracts, separate
dimension summaries, evaluator-validity results, and each finding contains:

- a check identifier;
- the evidence identifiers required by the contract;
- a status: `completed`, `skipped`, `refused`, `failed`, or `not_applicable`;
- a plain-language message;
- synthetic evidence identifiers;
- missing evidence identifiers; and
- `what_it_does_not_show`.

The last field prevents a green result from being read as stronger evidence than it is.

The Markdown output is a reviewable summary of agent results, dimension coverage, and
evaluator validity. It intentionally omits tool payloads.

## Why the baseline is included

The naive agent is not a production recommendation. It is a control comparison: a
reliability control is easier to understand when the report shows the failure it prevents.

## Relationship to the rest of the portfolio

This repository is a public umbrella for ideas demonstrated separately in:

- [`driftwood`](https://github.com/julie-elkins/driftwood) — benchmark design and
  reproducible scoring;
- [`llm-eval-validity`](https://github.com/julie-elkins/llm-eval-validity) — checking
  whether an evaluator deserves trust;
- [`abstention-eval`](https://github.com/julie-elkins/abstention-eval) — measuring
  refusal behaviour;
- [`fail-closed`](https://github.com/julie-elkins/fail-closed) and
  [`never-fired`](https://github.com/julie-elkins/never-fired) — proving that safeguards
  ran and failed safely; and
- [`mcp-server-design-guide`](https://github.com/julie-elkins/mcp-server-design-guide) —
  designing tool contracts that carry caveats with results.

The project does not contain internal certification content, internal prompts, provider
credentials, or copied production traces.

## Scope and limitations

This phase is deterministic and offline. It does not measure live model behaviour,
provider differences, latency, cost, or multi-agent coordination. The MCP server is local
and read-only; there is no hosted dashboard, leaderboard, authentication, or production
integration. A passing guarded baseline proves only that these synthetic contracts
distinguish the planted failures; it does not establish general agent reliability. CI
proves only that the checked-in synthetic fixture and adapter continue to satisfy the
current contracts; it does not prove a live agent will emit the same trace.

## Licence

MIT.
