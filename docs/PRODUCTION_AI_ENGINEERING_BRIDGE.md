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
telemetry and evaluation
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
4. name the telemetry needed to detect and investigate a failure;
5. choose containment and staged recovery actions; and
6. state what a synthetic lab does not prove about a live deployment.

## Learner checkpoint

Explain this sentence in your own words:

> A production-shaped workflow is not trustworthy because it completed. It is
> trustworthy only to the extent that its data, authority, evidence, evaluation, and
> recovery boundaries are observable and reviewable.

Then answer:

- What would you preserve before changing the workflow?
- Which action would you block pending approval?
- Which evidence would be missing if the system recorded only the final answer?
- What regression test would you run after recovery?

## Limits

This bridge uses a deterministic local fixture. It does not:

- call a model provider;
- access a network, database, queue, or cloud account;
- prove a production deployment is safe;
- establish live monitoring or incident-response readiness; or
- measure learner adoption or business impact.

Run the companion exercise in
[`examples/production-ai-engineering-bridge-lab/`](../examples/production-ai-engineering-bridge-lab/README.md).
