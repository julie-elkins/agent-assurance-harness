# Local Claude experiment

This is a supervised, local-only external-validity check for the Agent Assurance
Harness. It sends the built-in synthetic scenario identifiers through the reviewed
Anthropic Messages API boundary and evaluates the returned identifier-only event
shape with the existing harness.

It is not the primary research result. The deterministic synthetic protocol remains
the reproducible paper artifact. A live run can show provider variance and adapter
compatibility; it cannot establish general model quality, production reliability, or
causality.

## Before running

Set `ANTHROPIC_API_KEY` in the current shell process. Do not put the key in a file,
command argument, commit, issue, report, or CI secret for this local experiment.

The adapter requires `--allow-network`, allows up to three bounded conversation
turns per case, does not retry, and has a hard aggregate planning ceiling. A turn
may contain a synthetic tool request; the local harness executes that synthetic
tool and sends back only its status and identifiers. The adapter accepts either
the reviewed text-JSON event shape or a native Anthropic `tool_use` block. Native
tool calls use strict tool schemas with an empty input object, and the follow-up
uses native `tool_result` blocks containing only identifier-level result metadata;
raw tool arguments and raw tool results are refused. The local loop also disables
parallel tool calls so each synthetic observation is paired and bounded before the
next request. Provider `caller` metadata is accepted only as bounded identifiers
and discarded before the public trace.
Raw prompts, responses, and credentials are discarded after identifier-only
normalization. The accepted output contract is versioned as schema `1` and is
validated locally before the result reaches the harness evaluator. Lifecycle hooks
(deterministic checks at request, response, tool, and stop boundaries) record only a
safe refusal stage such as `before_request`, `after_response`, `before_tool`,
`after_tool`, `request_transport`, or `stop`. This separates a model contract
failure from a harness or budget refusal without retaining provider content.

## Ten-case smoke run

The smoke run executes one case for each built-in scenario:

```bash
uv run python tools/claude_local_experiment.py \
  --smoke \
  --model claude-sonnet-5-5 \
  --allow-network \
  --markdown
```

## Twenty-to-thirty-case pilot

The pilot repeats the fixed built-in scenario order to make provider variance
visible. Thirty cases are the default. The worst-case planning estimate is
`30 cases × 3 turns × $0.05 = $4.50`, below the five-dollar ceiling:

```bash
uv run python tools/claude_local_experiment.py \
  --pilot \
  --case-count 30 \
  --model claude-sonnet-5-5 \
  --allow-network \
  --max-total-cost-usd 5 \
  --markdown \
  --output /tmp/claude-sonnet-5-5-pilot.json
```

For replication, rerun the same pilot with the approved Haiku model identifier:

```bash
uv run python tools/claude_local_experiment.py \
  --pilot \
  --case-count 30 \
  --model claude-haiku-5-5 \
  --allow-network \
  --max-total-cost-usd 5 \
  --markdown \
  --output /tmp/claude-haiku-5-5-pilot.json
```

The report's cost is a conservative planning estimate, not a billing statement.
Compare the provider dashboard after the run if an accounting record is needed.
The report is useful only alongside the model identifier, case count, refusal count,
and limitations; it must not be presented as a benchmark or production claim.

## Structured-output comparison condition

The frozen baseline uses prompt instructions plus local schema validation. To test
whether provider-enforced formatting changes protocol acceptance, run the same
matrix with `--structured-output`:

```bash
uv run python tools/claude_local_experiment.py \
  --pilot \
  --case-count 30 \
  --model claude-sonnet-5-5 \
  --allow-network \
  --max-total-cost-usd 5 \
  --structured-output \
  --markdown \
  --output /tmp/claude-sonnet-structured-pilot.json
```

This is a separate comparison condition, not a replacement for the frozen
baseline. The local evidence validator remains authoritative, so a provider
that produces valid JSON can still fail a scenario's evidence contract.
