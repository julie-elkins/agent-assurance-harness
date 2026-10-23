# Production AI engineering bridge lab

This is a short, offline lab for learners who have built an agent workflow and now
need to reason about operating it. It connects data, access, deployment, telemetry,
evaluation, authorization, guardrail coverage, privacy, and incident recovery in one
synthetic scenario.

**Telemetry** means the structured operational evidence needed to understand what a
system did. This lab emits identifiers and bounded status metadata only; it does not
emit prompts, tool arguments, provider output, or real telemetry.

## What you will learn

You will trace a bounded support-agent workflow through:

```text
data → retrieval → model → tool → authorization → external action
      → telemetry → evaluation → incident response
```

The scenario contains a realistic-looking failure: retrieval returns an empty context
after a transport-success response, while the workflow still has a proposed external
ticket action. The guarded path records the semantic failure, blocks the action,
preserves bounded evidence, contains the workflow, and stages recovery for human
review. It also checks bounded retry, cost, and latency targets.

**Semantic outcome** means whether the requested task actually achieved its goal. It is
different from transport status, which only says whether a request returned.

## Run it

From the repository root:

```bash
uv run python examples/production-ai-engineering-bridge-lab/run_lab.py
```

The lab uses only the Python standard library and the checked-in synthetic fixture.
It makes no network calls and does not require credentials.

## Expected result

The output should show:

- the data contract and access check were observed;
- the retrieval request returned transport status `ok`;
- the semantic outcome was `empty_context`;
- the proposed external action was `blocked_pending_approval`;
- guardrail coverage included the input, handoff, tool, and external-action boundaries;
- the required control failed closed when execution authority was missing;
- telemetry recorded the bounded evidence identifiers;
- privacy output remained identifier-only and the reviewer-facing decision reason was
  recorded;
- retry, estimated cost, and latency stayed within the synthetic operating targets;
- the synthetic incident was `contained`;
- recovery was `staged_for_human_review`; and
- the result does not claim production readiness.

The command returns a nonzero exit code if those controls drift.

## Evidence to inspect

Compare these fields in the output:

- `data_contract`
- `access_check`
- `transport_status`
- `semantic_outcome`
- `tool_scope`
- `execution_authority`
- `guardrail_coverage`
- `telemetry`
- `evaluation`
- `privacy`
- `operating_targets`
- `incident_response`
- `what_it_does_not_prove`

The key observation is that transport status is `ok` while the task outcome is not
usable. The workflow must not turn that combination into an external write.

## Learner exercise

After running the lab, write a short answer to each question:

1. Which evidence would be needed to reconstruct the failed run?
2. Why is the proposed ticket action blocked?
3. Which guardrail boundaries must be covered before release?
4. Which boundary is outside the model?
5. What privacy or retention rule limits the evidence?
6. What should happen before the workflow is released again?
7. Which claim would be dishonest if added to the report?

## Learner checkpoint

You are ready to continue when you can explain why all five of these statements are
different:

1. The request returned.
2. The retrieved context was usable.
3. The agent proposed an action.
4. The action was authorized.
5. The system is ready to resume.

## Troubleshooting

If the command fails:

1. Run it from the repository root.
2. Confirm the project environment is available with `uv sync --extra dev`.
3. Confirm the script path is
   `examples/production-ai-engineering-bridge-lab/run_lab.py`.

If the expected status changes, inspect the script and tests before changing the
expected output. The lab is a teaching contract, not a report that should be made green
by weakening its assertions.

## What this does not prove

This is an offline synthetic teaching exercise. It does not establish live model
quality, production observability, security approval, rollback capability, or business
impact.

For the conceptual guide, read
[`docs/PRODUCTION_AI_ENGINEERING_BRIDGE.md`](../../docs/PRODUCTION_AI_ENGINEERING_BRIDGE.md).
