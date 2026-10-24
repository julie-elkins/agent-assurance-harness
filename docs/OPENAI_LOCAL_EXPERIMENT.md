# Local OpenAI replication

This is a supervised, local-only external-validity check for the Agent
Assurance Harness. It sends built-in synthetic scenario identifiers through
the OpenAI Responses API boundary and evaluates the returned identifier-only
event shape with the existing harness.

It is not the primary deterministic research result. The synthetic protocol
remains the reproducible paper artifact. A live run can show provider variance
and adapter compatibility; it cannot establish general model quality,
production reliability, or causality.

## Before running

Set `OPENAI_API_KEY` in the current shell process. Do not put the key in a
file, command argument, commit, issue, report, or CI secret for this local
experiment.

The adapter requires `--allow-network`, allows up to three bounded Responses
turns per case, does not retry, and has a hard aggregate planning ceiling. A
turn may contain a native zero-argument function call; the local harness
executes that synthetic tool and sends back only status and identifier
metadata as a `function_call_output` item. Provider output is parsed in
memory and discarded after identifier-only normalisation.

The native tool loop and the final output condition are separate controls:

- function-call protocol: OpenAI native `function_call` and
  `function_call_output` items;
- baseline response condition: prompt instructions plus local validation;
- comparison response condition: provider-enforced JSON Schema plus the same
  local validation.

The local validator remains authoritative. Provider-accepted JSON can still
fail a scenario's evidence contract.

## Ten-case smoke run

The smoke run executes one case for each built-in scenario:

```bash
uv run python tools/openai_local_experiment.py \
  --smoke \
  --model gpt-5.6 \
  --allow-network \
  --markdown
```

## Thirty-case pilot

The pilot repeats the fixed scenario order three times. The maximum planning
estimate is `30 cases × 3 turns × $0.05 = $4.50`, below the five-dollar
per-arm ceiling:

```bash
uv run python tools/openai_local_experiment.py \
  --pilot \
  --case-count 30 \
  --model gpt-5.6 \
  --allow-network \
  --max-total-cost-usd 5 \
  --markdown \
  --output /tmp/openai-pilot.json
```

Run the second arm as a separate command:

```bash
uv run python tools/openai_local_experiment.py \
  --pilot \
  --case-count 30 \
  --model gpt-5.6 \
  --allow-network \
  --max-total-cost-usd 5 \
  --structured-output \
  --markdown \
  --output /tmp/openai-structured-pilot.json
```

The report's cost is a conservative planning estimate, not a billing
statement. Compare the provider dashboard separately if an accounting record
is needed. Do not rerun a refused case merely to make the report complete.
Record the refusal as part of protocol acceptance.

## Data boundary

The public repository stores counts, statuses, refusal codes, refusal stages,
and usage estimates only. It does not store model prompts, model responses,
function arguments, function results, private traces, or credentials. The
actual live-provider reports remain local to the executable experiment
repository.
