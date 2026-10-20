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

The core has no runtime dependencies. Python 3.10 or newer is supported.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
python -m agent_reliability_lab
python -m agent_reliability_lab --json
python -m agent_reliability_lab --json --mutations
python -m agent_reliability_lab --markdown
```

The default command reports both agents. Add `--fail-on-findings` when a caller wants the
deliberately naive baseline to produce a non-zero exit code:

```bash
python -m agent_reliability_lab --json --fail-on-findings
```

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
provider differences, latency, cost, or multi-agent coordination. It does not yet expose
an MCP adapter, hosted dashboard, leaderboard, or production integration. A passing
guarded baseline proves only that these synthetic contracts distinguish the planted
failures; it does not establish general agent reliability.

## Licence

MIT.
