# Production AI agent readiness checklist

This checklist is a review surface for the learning path. It connects the controls
already taught in the harness to the evidence a reviewer should inspect before making a
deployment decision.

It is not a certification, production approval, security sign-off, or claim that a
workflow is ready because every box is checked. A checklist can show that evidence was
observed. It cannot replace the people and policies that decide whether the remaining
risk is acceptable.

## How to use it

Review one row at a time. Record:

- the status;
- the evidence identifier or linked artifact;
- the reviewer and date;
- the owner of any missing evidence; and
- the next decision or re-check.

Use these status values:

| Status | Meaning | Decision consequence |
| --- | --- | --- |
| `observed` | The required evidence exists and matches the reviewed workflow and revision. | Continue the review; do not call this production approval. |
| `missing` | Required evidence was expected but was not observed. | Block the affected decision until the gap is resolved or explicitly accepted by the accountable owner. |
| `refused` | The control declined to proceed because its required input or authority was unsafe or incomplete. | Preserve the refusal and escalate; do not turn it into a pass. |
| `not_established` | The control or claim has not been tested for this workflow. | Make no readiness claim about that dimension. |

An **evidence contract** is the minimum observable evidence required before a workflow
may claim that a task, control, or recovery step passed. An empty field is not evidence
that the check passed.

## 1. System boundary and ownership

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| Workflow boundary | What workflow is being reviewed, and what is outside its boundary? | Workflow identifier, revision, entry points, external effects, and stated limits. | [Production AI Engineering Bridge](PRODUCTION_AI_ENGINEERING_BRIDGE.md) |
| Data and user impact | What data classes, users, and downstream decisions can be affected? | Data contract, access decision, retention rule, and bounded impact description. | [AI Incident Response](AI_INCIDENT_RESPONSE.md) |
| Decision ownership | Who owns containment, approval, communication, and restoration decisions? | Named owner, accountable approver, escalation path, and next review time. | [Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md) |

## 2. Hosting and delivery path

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| Runtime boundary | Where does the workflow run, and what identities can invoke it? | Deployment or runtime identifier, caller identity, permission boundary, and environment separation. | [Production Delivery Standard](../PRODUCTION_DELIVERY_STANDARD.md) |
| Change path | Can a second person understand, review, and reverse the change? | Versioned change, dependency evidence, required CI checks, approval record, and rollback path. | [Developer Workflow Assurance](DEVELOPER_WORKFLOW_ASSURANCE.md) |
| Dependency evidence | Were dependency and code-security checks observed for the reviewed revision? | Dependency review, code scanning, secret checks, and supply-chain evidence. | [Developer Workflow Assurance](DEVELOPER_WORKFLOW_ASSURANCE.md) |

## 3. Authorization and tool authority

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| Tool scope | What tools can the workflow call, and what can each tool change? | Tool contract, argument boundary, identity, scope, and external-effect description. | [Agent Workflow Teaching Lab](../examples/agent-workflow-teaching-lab/README.md) |
| Execution authority | What independent control permits a proposed action to change external state? | Approval or authorization decision bound to the exact action and current revision. | [AI Incident Response](AI_INCIDENT_RESPONSE.md) |
| Approval binding | Would approval become invalid if the recipient, amount, data, or action changed? | Exact-action approval evidence and mismatch behavior. | [Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md) |

## 4. Observability and privacy

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| Reconstruction | Could a reviewer reconstruct the run without receiving raw sensitive content? | Identifier-only trace for workflow, session, request, revisions, tool calls, decisions, and effects. | [AI Incident Response](AI_INCIDENT_RESPONSE.md) |
| Failure visibility | Would the system expose missing, skipped, refused, or failed checks? | Explicit status for each required control and an alert or escalation path. | [Agent Assurance Harness Guide](../GUIDE.md) |
| Privacy boundary | What must never enter the public report or broad status channel? | Data classification, redaction rule, retention decision, and public-output check. | [AI Incident Response](AI_INCIDENT_RESPONSE.md) |

## 5. Evaluation and semantic outcome

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| Task outcome | Did the requested task succeed, or did only the transport return successfully? | Separate transport status, semantic outcome, and missing-context behavior. | [Production AI Engineering Bridge Lab](../examples/production-ai-engineering-bridge-lab/README.md) |
| Evaluation coverage | Do evaluations include normal, edge, adversarial, and failure cases? | Dataset identifiers, expected outcomes, negative controls, and coverage result. | [LLM Eval Validity](https://github.com/julie-elkins/llm-eval-validity) |
| Repeatability | Will the evaluation run again when the model, prompt, data, tool, or policy changes? | Trigger, schedule, revision binding, threshold, and human review path. | [LLM Eval Validity](https://github.com/julie-elkins/llm-eval-validity) |
| Independent challenge | Can a breaker or verifier catch a false pass without sharing the builder's assumptions? | Independent control, known negative control, and blocked result. | [Agent Workflow Teaching Lab](../examples/agent-workflow-teaching-lab/README.md) |

## 6. Guardrails and untrusted input

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| Input boundary | Which documents, pages, messages, or tool results are untrusted data? | Classification, provenance identifier, and handling rule. | [AI Incident Response Tabletop Lab](../examples/ai-incident-response-lab/README.md) |
| Handoff coverage | Does each agent, handoff, tool, and external-action boundary have a control? | Boundary inventory and observed control result for every transition. | [Production AI Engineering Bridge Lab](../examples/production-ai-engineering-bridge-lab/README.md) |
| Fail-closed behavior | What happens when approval, telemetry, guardrail, or authorization is unavailable? | Refusal, block, escalation, or degraded-mode evidence. | [Agent Assurance Harness Guide](../GUIDE.md) |
| Retry safety | Can an ambiguous result amplify cost or external effects? | Retry count, idempotency or reconciliation evidence, cost ceiling, and stop condition. | [Production AI Engineering Bridge Lab](../examples/production-ai-engineering-bridge-lab/README.md) |

## 7. Human approval and production change management

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| High-risk approval | Which actions require a human decision before execution? | Risk classification, approval owner, exact-action binding, and unavailable-approver behavior. | [Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md) |
| Change classification | Is the change standard or emergency, and why? | Change record, reason, scope, success condition, failure condition, and approver. | [Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md) |
| Limited rollout | What is the narrowest canary, or limited rollout, that can test the change? | Audience or synthetic scope, monitored evidence, stop condition, and expansion decision. | [Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md) |
| Reversal | How will the team return to a known-good revision, and what external effects need reconciliation? | Rollback path, reconciliation owner, and verification result. | [Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md) |

## 8. Incident response and recovery

| Check | Question | Evidence to inspect | Related material |
| --- | --- | --- | --- |
| Containment | What can be paused, narrowed, revoked, or isolated before another side effect occurs? | Containment decision, timestamp, owner, and evidence-preservation result. | [AI Incident Response](AI_INCIDENT_RESPONSE.md) |
| Communications | Who receives the next update, what is known, what is uncertain, and when is the next update due? | Bounded status update, audience, owner, and update time. | [Advanced Production Operations](ADVANCED_PRODUCTION_OPERATIONS.md) |
| Recovery gate | What must be true before capability is restored? | Synthetic replay, approval boundary, regression case, canary result, and accountable restoration decision. | [AI Incident Response Tabletop Lab](../examples/ai-incident-response-lab/README.md) |
| Follow-up | What will change so the same failure is detected earlier? | Action owner, due date, regression control, and post-incident review record. | [AI Incident Response](AI_INCIDENT_RESPONSE.md) |

## Learner checkpoint

Choose one synthetic workflow from this repository and write a review packet containing:

1. the workflow and revision under review;
2. one evidence identifier for each of the eight sections;
3. one `missing`, `refused`, or `not_established` result;
4. the owner and approver for the next decision;
5. the narrowest safe recovery change; and
6. the evidence that would permit broader restoration.

The correct result may contain unresolved findings. A review that reports an unknown
state honestly is stronger than a green checklist that never checked the boundary.

## What this checklist does not prove

- It does not prove live model quality, production observability, security approval,
  rollback capability, business continuity, or learner completion.
- It does not replace an organization's incident plan, change policy, privacy review,
  legal process, or human sign-off.
- It does not authorize access to private data, external systems, or provider accounts.
- It does not turn a synthetic result into a production claim.

## First-party references

- [NIST SP 800-61 Revision 3: Incident Response Recommendations and Considerations for Cybersecurity Risk Management](https://csrc.nist.gov/pubs/sp/800/61/r3/final)
- [Google SRE: Managing Incidents](https://sre.google/sre-book/managing-incidents/)
- [OpenAI Agent Builder safety](https://developers.openai.com/api/docs/guides/agent-builder-safety)
- [Anthropic: Trustworthy agents](https://www.anthropic.com/research/trustworthy-agents)
