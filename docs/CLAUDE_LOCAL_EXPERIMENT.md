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

The adapter requires `--allow-network`, makes one request per case, does not retry,
and has a hard aggregate planning ceiling. Raw prompts, responses, and credentials
are discarded after identifier-only normalization.

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
visible. Thirty cases are the default:

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
