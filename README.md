# Agent Reliability Lab

An offline Agent Assurance Harness for testing tool-using AI agents.

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
size limits are configurable with `--timeout-seconds` and `--max-response-bytes`.

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

## Use it as an MCP server

The repository also exposes a small local MCP server (Model Context Protocol server: a
typed tool interface that an AI client can call). It has three read-only tools:

- `list_scenario_packs` validates and lists the built-in synthetic packs.
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
