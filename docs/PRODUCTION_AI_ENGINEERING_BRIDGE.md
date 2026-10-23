# Production AI engineering bridge

This bridge connects an AI workflow that works locally to one that can be operated
responsibly. It is a learner guide, not a production deployment recipe or a claim that
the synthetic controls prove live system safety.

## Why this bridge exists

A learner can build an agent that returns an answer and still miss the operational
questions that determine whether the system is safe to run:

- Which data did the workflow use?
- Was the data allowed for this task?
- Which model, prompt, tool, and policy versions were active?
- What external action could the workflow take?
- Which control independently authorized that action?
- What evidence would show that the workflow failed?
- How would an operator contain, recover, and test the change?

**LLMOps** means the operational practices for monitoring, evaluating, versioning,
cost-controlling, and recovering AI systems. The bridge teaches those practices with
metadata-only synthetic evidence.

**Observability** means being able to reconstruct what happened from bounded evidence.
**Controllability** means being able to stop, isolate, narrow, or recover the workflow.
Both are required: a system that can be observed but not stopped is not operationally
controlled, and a system that can be stopped but not reconstructed cannot be reliably
investigated.

## Lifecycle

```text
data contract
    ↓
access check
    ↓
retrieval and model execution
    ↓
tool scope and execution authority
    ↓
guardrail coverage across handoffs
    ↓
telemetry, evaluation, and bounded operating targets
    ↓
failure detection
    ↓
containment and evidence preservation
    ↓
staged recovery and human review
```

The important boundary is **execution authority**: the independent permission that
allows a proposed transition to change external state. A model producing a tool call is
not the same thing as that tool call being authorized.

## Learner objectives

After completing the bridge, a learner should be able to:

1. identify the data, model, tool, policy, and version identifiers needed to reconstruct
   a workflow;
2. separate a successful transport response from a successful task outcome;
3. describe the minimum authority needed for a proposed external action;
4. identify whether guardrails cover every agent, handoff, tool, and external-action
   boundary;
5. name the telemetry needed to detect and investigate a failure;
6. choose containment and staged recovery actions;
7. explain how privacy, retention, and reviewer transparency constrain the design; and
8. state what a synthetic lab does not prove about a live deployment.

## Learner checkpoint

Explain this sentence in your own words:

> A production-shaped workflow is not trustworthy because it completed. It is
> trustworthy only to the extent that its data, authority, evidence, evaluation, and
> recovery boundaries are observable and reviewable.

Then answer:

- What would you preserve before changing the workflow?
- Which action would you block pending approval?
- What should happen if the approval or telemetry path is unavailable?
- Which evidence would be missing if the system recorded only the final answer?
- Which cost, latency, retry, and reliability target would you monitor?
- What regression test would you run after recovery?

## Readiness checklist

Use the [Production AI Agent Readiness Checklist](PRODUCTION_AI_AGENT_READINESS_CHECKLIST.md)
as a capstone review after running the bridge lab. It maps the evidence questions across
system ownership, delivery path, authorization, observability, evaluation, guardrails,
human approval, change management, incident response, and recovery.

The checklist is a review surface, not a green-light mechanism. A `missing`, `refused`,
or `not_established` result remains visible instead of being converted into a pass.

## Limits

This bridge uses a deterministic local fixture. It does not:

- call a model provider;
- access a network, database, queue, or cloud account;
- prove a production deployment is safe;
- establish live monitoring or incident-response readiness; or
- measure learner adoption or business impact.

Run the companion exercise in
[`examples/production-ai-engineering-bridge-lab/`](../examples/production-ai-engineering-bridge-lab/README.md).
