# AI incident response tabletop lab

This is a short synthetic tabletop exercise for Part 4 of the
[Agent Evaluation Learning Path](https://github.com/julie-elkins/agent-evaluation-learning-path).

It teaches how to reason about an AI incident without pretending that a local fixture
is production telemetry. A tabletop exercise is a structured scenario discussion:
learners identify decisions, evidence, owners, and containment steps before they
automate anything.

## Scenario

`agent-run-001` is a document-ingestion workflow. It reads `source-doc-001`, produces
an internal summary, and has access to a synthetic `publish-summary` tool.

The workflow reports transport success. During the run:

1. instruction-like content enters through the untrusted document;
2. the workflow proposes `tool-call-001` to publish a summary;
3. no valid execution authority is observed for the proposed external state change;
4. a later context lookup returns an empty result and a naive path retries.

The scenario is intentionally abstract. It contains no document text, prompt, model
output, credentials, destination, or real telemetry.

## Learner objective

By the end, you should be able to:

- distinguish runtime security, model safety/alignment, and execution authority;
- identify the first safe containment action;
- name the evidence needed to reconstruct the run;
- describe what containment does not undo;
- propose a regression test and a staged recovery decision.

## Run the existing offline controls

From the repository root:

```bash
uv run python -m agent_reliability_lab --list-packs --markdown
uv run python examples/agent-workflow-teaching-lab/run_lab.py
```

The first command lists the built-in synthetic scenario packs. The second runs the
transport-success/empty-context control. Both commands are offline.

For this tabletop, inspect the built-in scenario identifiers:

- `misleading-tool-output`
- `unauthorized-side-effect`
- `http-200-empty-context-retry`

The lab does not add a provider SDK, make a network request, or persist real payloads.

## Tabletop questions

Answer these before reading the expected result:

1. What should be stopped first: the model, the tool, the data source, the retry loop,
   or all of them?
2. What evidence identifies the active model, prompt, policy, tool, and configuration
   revisions?
3. What proves that the proposed publication action had execution authority?
4. What external effect may already have happened, and what identifier would let a
   responder reconcile it?
5. Which control distinguishes untrusted content from an instruction?
6. What must be true before access is restored?

## Expected learner result

A strong answer should:

- pause the workflow and external tool before allowing another side effect;
- preserve identifier-only evidence for the run, source, revisions, tool call,
  authorization decision, and external-effect state;
- treat the document and tool result as untrusted data, not operating instructions;
- stop retry amplification when task evidence is empty or ambiguous;
- distinguish a blocked action from proof of model alignment;
- restore capability only after a bounded synthetic replay, an observed approval boundary,
  and a regression case for the failure.

## Checkpoint

Explain this sentence in your own words:

> Transport success tells you that a request returned. It does not tell you that the
> task was safe, authorized, complete, or reversible.

Then explain why an incident record that contains only a final answer cannot reconstruct
what the model saw, what it attempted, or which control allowed the action.

## Advanced organizational exercise

Continue with the
[Advanced Production Operations lesson](../../docs/ADVANCED_PRODUCTION_OPERATIONS.md)
to add ownership, communications, and production change management to this scenario.

Assign an incident commander, technical lead, security/privacy lead, product owner,
communications lead, scribe, and change approver. In a small team, one person may hold
several roles, but do not let the person who made a high-risk change be the only person
who approves it.

Answer these questions:

1. Who owns the next containment decision?
2. Who can pause the workflow and external tool?
3. What is the first bounded internal update, and when is the next update due?
4. Which detail belongs only in the restricted evidence record?
5. Is the recovery action a standard or emergency change?
6. What is the narrowest canary scope?
7. What result stops the canary or triggers rollback?
8. Who approves broader restoration?

The expected answer must name an owner for every decision, distinguish responsibility
from approval authority, preserve identifier-only evidence, and state what the recovery
change does not undo.

## What this lab does not prove

This is a synthetic teaching exercise. It does not prove live model behavior, production
monitoring, security readiness, incident containment, rollback, or learner completion.
