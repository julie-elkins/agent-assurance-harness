# Agent Workflow Teaching Lab

This is the ten-minute path through the Agent Assurance Harness.

It teaches a common evaluation failure: a request returns transport success, but
the task still failed because the returned context was empty. **Semantic outcome**
means whether the requested task actually achieved its goal; it is separate from
whether the request returned successfully.

## What you will learn

The lab has three roles:

1. **Bounded executor** -- runs the workflow within declared retry and estimated-cost
   ceilings.
2. **Independent breaker** -- checks whether a green-looking run hides a semantic
   failure.
3. **Human approver** -- remains responsible for the escalated decision.

## Run it

From the repository root:

```bash
uv run python examples/agent-workflow-teaching-lab/run_lab.py
```

The expected result is:

- the naive path is `failed`;
- the guarded path is `completed`;
- both paths report transport status `ok`;
- the naive path records three retries and exceeds its synthetic ceilings;
- the guarded path records `escalated` and stays within its ceilings;
- human approval remains required.

The output contains identifiers, classifications, counts, and bounded numeric
metadata only. It does not contain prompts, tool arguments, tool payloads, credentials,
provider output, or real telemetry.

## Workflow map

```text
synthetic request
       |
       v
bounded executor -----> transport result: ok
       |                         |
       |                         v
       |                  semantic outcome check
       |                    /              \
       |             usable context      empty context
       |                  |                   |
       v                  v                   v
independent breaker   complete         stop, record, escalate
       |
       v
human approval remains outside the automated result
```

## Evidence to inspect

Compare these fields in the output:

- `transport_status`
- `semantic_outcome`
- `workflow_id`
- `retry_count`
- `estimated_cost_usd`
- `finding_status`
- `missing_evidence`

The important observation is that `transport_status: "ok"` appears in both paths.
Only the guarded path records a safe semantic disposition and stays inside its
declared bounds.

## Troubleshooting

If the command fails:

1. Run it from the repository root.
2. Confirm the project environment is available with `uv sync --extra dev`.
3. Confirm the scenario identifier is
   `http-200-empty-context-retry`.
4. Run the focused checks:

```bash
uv run pytest tests/unit/test_scenarios.py tests/unit/test_evaluators.py -q
```

If the guarded path becomes `failed`, the evaluator or the synthetic contract has
drifted. Do not update the expected output to make the lab green; inspect which
required evidence disappeared.

## What this does not prove

This is an offline synthetic teaching control. It does not establish live model
quality, production monitoring, semantic truth outside the declared contract,
business impact, or the number of people who use the material.

For the reusable design decisions, see the
[Agent Systems Design Guide](https://github.com/julie-elkins/agent-systems-design-guide).
