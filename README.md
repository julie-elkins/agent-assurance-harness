# Agent Reliability Lab

An offline evidence-contract test harness for tool-using AI agents.

An evidence contract is the minimum set of observable facts required before an agent may
claim that a task is complete. The question is not only whether an agent produced an
answer. It is whether the agent can show:

- which tool it used;
- which required checks actually ran;
- when evidence was missing;
- when it refused instead of guessing; and
- what the result still does not prove.

The first milestone compares a deliberately naive agent with a guarded agent across three
synthetic cases:

1. **Tool misuse** — a plausible result comes from the wrong tool.
2. **False completion** — the agent claims all checks ran when one did not.
3. **Answering without evidence** — the agent answers instead of abstaining when a lookup
   returns no usable record.

An abstention is a deliberate refusal to answer because the available evidence is
insufficient.

The harness also runs controlled evidence mutations. A mutation is a deliberate change to
a synthetic trace, such as removing a required verification call, used to test whether the
evaluator catches a known failure instead of silently passing it.

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
```

The default command reports both agents. Add `--fail-on-findings` when a caller wants the
deliberately naive baseline to produce a non-zero exit code:

```bash
python -m agent_reliability_lab --json --fail-on-findings
```

## Report contract

The JSON report is intentionally small. It includes the scenario contracts and each
finding contains:

- a check identifier;
- the evidence identifiers required by the contract;
- a status: `completed`, `skipped`, `refused`, `failed`, or `not_applicable`;
- a plain-language message;
- synthetic evidence identifiers;
- missing evidence identifiers; and
- `what_it_does_not_show`.

The last field prevents a green result from being read as stronger evidence than it is.

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

This milestone is deterministic and offline. It does not measure live model behaviour,
provider differences, latency, cost, prompt injection, or multi-agent coordination. A
passing guarded baseline proves only that these three synthetic contracts distinguish the
planted failures; it does not establish general agent reliability.

## Licence

MIT.
