# AI incident response

This guide teaches how to adapt an incident-response lifecycle to an AI-enabled
workflow. It is a learner guide, not a production runbook, security approval, or
claim that a model is safe.

## Why AI incidents need an additional layer

Traditional cloud incident response asks which account, identity, workload, network
path, or resource was affected. AI incident response asks those questions and also
reconstructs:

- the model, prompt, policy, tool, and configuration revisions;
- the context, document, memory, retrieval result, or tool result that influenced the run;
- which tool calls were proposed, allowed, blocked, retried, or completed;
- what approval or authorization allowed a proposed action to change external state;
- whether the behavior changed without an infrastructure change;
- whether the workflow can be stopped and reconstructed without exporting sensitive data.

Keep three boundaries separate:

1. **Runtime security** — controls outside the model, such as identity, permissions,
   sandboxing, network limits, and logging.
2. **Model safety and alignment** — behavior inside the model, including whether it
   follows the intended task and refuses unsafe requests.
3. **Execution authority** — the independent decision about whether a proposed action
   may change external state.

A successful external block proves that a control acted. It does not prove that the
model was aligned or that the underlying input was safe.

## Evidence contract

An evidence contract is the minimum observable evidence required before a response or
recovery decision can pass. For an AI incident, preserve identifiers and bounded
metadata for:

- incident, workflow, session, and request;
- model, prompt, policy, tool, and configuration revisions;
- source and retrieval identifiers and lineage;
- tool-call names, authorization decisions, and result status;
- approval, refusal, escalation, containment, and recovery decisions;
- external-effect identifiers and rollback or reconciliation state;
- timestamps, owners, and the sequence needed to reconstruct the event.

Do not place prompts, document text, model output, secrets, credentials, or customer
data in this public lab. If private investigation needs the payload, keep it in the
approved private evidence system and reference only its identifier here.

## Seven-phase response path

### 1. Preparation

Define owners, escalation paths, data classifications, model and tool inventories,
permission boundaries, approval requirements, stop controls, retention rules, and the
metadata needed to reconstruct a run.

Test that the stop control and alert path actually fire. A control that has never
fired is a hypothesis, not evidence.

### 2. Identification

Classify the event as a possible security, safety, privacy, reliability, or governance
incident. Record confidence without overstating it. Identify the affected workflow,
revisions, untrusted inputs, tool calls, approval decisions, and known external effects.

### 3. Containment

Stop or narrow the workflow before more side effects occur. Possible actions include:

- disable a tool or connector;
- revoke or narrow a credential;
- isolate a data source;
- freeze a prompt, policy, model, or retrieval revision;
- pause retries;
- require human approval for every external action.

Containment must preserve evidence and state what it does not undo. Stopping a workflow
does not reverse an action that already committed.

### 4. Investigation

Reconstruct the chain from input and context through model decision, policy evaluation,
tool call, authorization, and external effect. Compare the affected revision with a
known-good baseline. Separate model behavior from tool behavior, authorization
behavior, and infrastructure behavior.

### 5. Eradication

Remove or quarantine the unsafe input, correct the permission or policy boundary,
rotate or revoke exposed credentials, patch the tool or dependency, and update the
model, prompt, retrieval, or configuration through the approved change path. Add a
regression case that would have caught the incident.

### 6. Recovery

Restore capability in stages. Start with the narrowest permissions and a bounded
synthetic replay. Confirm that refusal, approval, containment, rollback, and evidence
controls still work before restoring broader capability.

### 7. Follow-up

Record the timeline, evidence gaps, decisions, residual risk, and owners. Update the
incident plan, evaluations, threat model, tool contracts, and training material.
Exercise the new control so the change is observable.

## Tabletop lab

The companion [AI Incident Response Tabletop Lab](../examples/ai-incident-response-lab/README.md)
uses only synthetic identifiers and the harness's existing offline scenarios.

For the organizational layer, continue to
[Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md). It adds ownership,
bounded communications, emergency changes, canary rollout, rollback, and recovery
approval without turning the public lesson into a production runbook.

After the tabletop, use the
[Production AI Agent Readiness Checklist](PRODUCTION_AI_AGENT_READINESS_CHECKLIST.md)
to cross-check the evidence that should exist before a recovery or deployment decision.

The lab combines three failure signals:

- `misleading-tool-output` — untrusted content is treated as an instruction;
- `unauthorized-side-effect` — a proposed external action lacks execution authority;
- `http-200-empty-context-retry` — transport success hides a failed task outcome and
  unsafe retry amplification.

The goal is not to diagnose a real incident. The goal is to practice asking what must
be stopped, what evidence must be preserved, what authority must be revoked, and what
regression test should prevent recurrence.

## What this guide does not prove

- It does not establish live model quality or alignment.
- It does not prove production observability, containment, or rollback.
- It does not replace an organization's incident plan, security review, or legal process.
- It does not authorize access to private data or external systems.
- It does not validate claims from social posts or vendor announcements.

## First-party references

- [NIST AI Incident Response Guidebook](https://www.nist.gov/document/iqt-ai-incident-response-guidebook-0)
- [OpenAI Agent Builder safety](https://developers.openai.com/api/docs/guides/agent-builder-safety)
- [Anthropic Trustworthy agents](https://www.anthropic.com/research/trustworthy-agents)
