# AI evaluation incident response

This guide teaches how to respond when an evaluation, evaluator, evidence path,
or release gate can no longer support the decision it was supposed to inform.
It is a learner guide for synthetic, metadata-only examples. It is not a
production runbook, a security approval, or proof that a model or evaluator is
safe.

## What is an evaluation incident?

An evaluation incident is a condition in which the measurement system is no
longer trustworthy for its declared decision.

The failure may be in:

- the model or agent behavior;
- the case set or test data;
- the evaluator or judge;
- the telemetry or evidence path;
- the decision rule or release gate; or
- the ownership and response process.

This distinction matters. A model regression and an evaluator regression do not
have the same containment action. If a score drops because the evaluator lost
required evidence, changing the model may make the real problem harder to see.

## Runtime incident versus evaluation incident

These incidents can overlap, but they ask different questions:

| Incident type | Primary question | Example | First concern |
|---|---|---|---|
| Runtime AI incident | What did the agent do, and what may it have affected? | An agent proposed an unauthorized tool action. | Stop further side effects and preserve the run evidence. |
| Evaluation incident | Can the evaluation support the decision we are about to make? | A green report omitted the required tool-authorization evidence. | Quarantine the result and hold the release decision. |
| Combined incident | Did unsafe behavior and an invalid measurement path occur together? | A missing tool span hid a policy violation. | Contain the workflow and the evaluation pipeline in parallel. |

If a runtime safety, privacy, security, or external-side-effect event may have
occurred, use the [AI Incident Response guide](AI_INCIDENT_RESPONSE.md) as
well as this guide.

## The first questions to ask

Before interpreting a score, write down:

1. What decision was this evaluation meant to support?
2. What evidence was required for that decision?
3. Which revision of the model, prompt, policy, tools, data, case set, and
   evaluator produced the result?
4. Which evidence was actually observed?
5. What is missing, invalid, stale, or outside the declared scope?
6. Could the result be a behavior change, a measurement change, or both?
7. What action must stop until the uncertainty is resolved?

The first question prevents an evaluation incident from becoming a discussion
about a score without a decision. The revision questions prevent a result from
being compared with a different system or protocol.

## Signals, meaning, and first action

Use this table as a triage surface. Triage means sorting an event by likely
cause and urgency before choosing a response.

| Signal | What it may mean | First action | Decision consequence |
|---|---|---|---|
| A report is green but required evidence is missing | False green: the report claims success without observing every required check | Quarantine the report and mark the missing evidence explicitly | Do not use the result for release approval |
| A pass rate changes only on one high-risk slice | A localized behavior regression, case-mix change, or coverage problem | Compare the slice with the prior revision and inspect the cases | The aggregate score cannot override the high-risk slice |
| Judge disagreement or override rate rises | Rubric drift, judge drift, ambiguous criteria, or a changed task distribution | Pause automated decisions and run calibration or human review | Hold or narrow the decision until validity is restored |
| The case set changed without a declared revision | Protocol drift or possible test contamination | Freeze the comparison and identify the exact case-set revision | Do not compare the result with the previous baseline |
| Tool, state, or terminal spans are absent | Observability failure, not necessarily agent success | Treat the affected result as incomplete and repair instrumentation | The result is not sufficient for a clean pass |
| The evaluator cannot run or returns no result | Evidence is unavailable, not a passing result | Record the unavailable status and stop the dependent gate | Hold the release or route to an approved fallback |
| A privacy or redaction check fails | Evaluation evidence may expose restricted content | Restrict access, preserve bounded identifiers, and stop export | Do not publish, reuse, or broaden the evidence |
| A result passes but high-risk cases were not tested | The claim is broader than the evidence | Narrow the claim or add the missing cases | Release only within the tested scope |
| A regression gate fails open | The control path can approve when a required check is absent | Disable the gate or require human approval | Treat the release decision as invalid |

Do not silently convert an unavailable or invalid result into a zero, an
average, or a pass. Preserve the distinction between a failed check and a
check that could not be evaluated.

## Response lifecycle

### 1. Declare the affected decision

Name the decision that may be invalid:

- release or rollback;
- prompt, model, policy, tool, or retrieval change;
- evaluator or rubric revision;
- benchmark comparison;
- production monitoring response; or
- human-approval readiness.

Record what is blocked and what remains safe to use. A report may still be
useful for investigation while being invalid for release approval.

### 2. Detect and classify

Classify the event as one or more of:

- **behavior** — the model or agent acted incorrectly or unsafely;
- **coverage** — important cases were absent or unrepresentative;
- **evaluator** — the judge, rubric, deterministic check, or aggregation rule
  was invalid or changed;
- **evidence** — required observations were missing, malformed, stale, or
  bound to the wrong revision;
- **telemetry** — the instrumentation, collector, storage, or query path
  dropped or altered evidence;
- **governance** — ownership, approval, communication, or change control was
  missing.

Do not force one label when the incident has multiple causes. A missing trace
may hide a behavior failure, so the evidence problem and the possible behavior
problem must remain separate findings.

### 3. Contain the decision path

Containment means stopping the affected decision from causing more impact. The
appropriate action may be to:

- hold a release or rollback decision;
- quarantine the affected report or case set;
- disable automated approval;
- pause a judge, evaluator, or regression gate;
- require human review;
- narrow the claim to the observed slice; or
- stop the workflow if a runtime safety or side-effect risk is also present.

Containment does not repair the evaluator and does not reverse an external
effect that already occurred.

### 4. Preserve bounded evidence

Preserve identifiers and metadata needed to reconstruct the measurement:

- incident, run, workflow, and request identifiers;
- model, prompt, policy, tool, data, case-set, and evaluator revisions;
- manifest or digest that binds the result to those revisions;
- required evidence fields and observed or missing status;
- case slices, counts, thresholds, and decision rules;
- judge calibration and disagreement metadata;
- timestamps, owners, and the containment decision.

Do not copy prompts, customer data, raw model output, credentials, raw tool
arguments, or restricted documents into this public repository or a public
incident report.

### 5. Investigate the boundary

Compare the affected run with a known-good revision and ask:

- Did behavior change while the evaluation protocol stayed constant?
- Did the protocol, rubric, judge, aggregation, or case set change?
- Did the evidence producer emit all required fields?
- Did the collector, storage, redaction, or query path alter the evidence?
- Did the decision rule fail open, ignore a missing field, or use the wrong
  threshold?
- Was the result used outside the workflow, revision, slice, or date for which
  it was valid?

Separate observed facts from hypotheses. A plausible cause is not a confirmed
finding until the relevant evidence is checked.

### 6. Remediate

Choose the smallest correction that addresses the confirmed boundary:

- repair or pin the case-set manifest;
- restore required instrumentation;
- correct a deterministic check or aggregation rule;
- recalibrate or replace a judge;
- add an independent breaker or negative control;
- repair redaction, retention, or access controls;
- fix the release gate or approval path; or
- correct the model, prompt, policy, tool, or retrieval behavior.

If the correction changes the evaluation itself, treat it as a new evaluator
revision. Do not compare the repaired result with the old result without
recording the protocol change.

### 7. Re-evaluate

Run, in order appropriate to the risk:

1. the affected case and a deliberately degraded negative control;
2. the representative case set;
3. the high-risk and boundary slices;
4. a held-out set when the evaluator or case design changed;
5. the telemetry and evidence-completeness checks; and
6. the runtime security or side-effect checks if the incident crossed that
   boundary.

The negative control is a planted failure that should be caught. If it passes,
the evaluator is not ready to support the original decision.

### 8. Decide what happens next

The result should produce an explicit disposition:

- **release** — evidence supports the declared decision within scope;
- **hold** — required evidence or approval is unresolved;
- **revise** — a correction is required before the evaluation can be trusted;
- **rollback** — return to a known acceptable revision;
- **narrow** — keep the result but reduce the claim to the tested scope; or
- **retire** — stop using an invalid metric, judge, case set, or gate.

The disposition must name an owner, the next evidence required, and the review
date. A report without an owner is a historical artifact, not a control.

### 9. Learn and prevent recurrence

Close the incident only after recording:

- the confirmed failure boundary;
- the evidence that supports the finding;
- evidence that remains unavailable;
- the containment and remediation actions;
- the affected decision and scope;
- the new regression case or control;
- the owner and review date.

The follow-up case should fail if the same condition returns. Do not close the
incident merely because the dashboard is green again.

## Minimal incident record

Use this template for a synthetic exercise or as a starting point for an
organization's own approved record:

```yaml
incident_id: eval-incident-001
decision_affected: release
workflow_id: synthetic-workflow-001
severity: high
trigger: required_evidence_missing
classification:
  - evidence
  - governance
affected_revisions:
  model: model-rev-001
  prompt: prompt-rev-001
  policy: policy-rev-001
  tools: tools-rev-001
  data: data-rev-001
  case_set: cases-rev-002
  evaluator: evaluator-rev-003
observed_evidence:
  - run_manifest
  - case_counts
missing_evidence:
  - tool_authorization
containment_action: hold_release_and_quarantine_report
owner: synthetic-owner
next_evidence:
  - restored_tool_authorization_span
  - negative_control_result
  - held_out_case_result
disposition: hold
regression_case_id: regression-missing-evidence-001
review_date: 2026-11-02
```

The example is synthetic. Replace it with the organization's approved incident
system, access controls, retention rules, and escalation process before relying
on it operationally.

## Relationship to the course

The public [LLM & Agent Evaluation Lab](https://github.com/julie-elkins/claude-evaluation-lab)
uses this guide to connect operational signals to an evaluation decision. The
course keeps the required path offline and synthetic.

For a runnable runtime scenario, use the
[AI Incident Response Tabletop Lab](../examples/ai-incident-response-lab/README.md).
For the evaluation boundary, use this guide to ask whether the evidence itself
can still support the decision.

## What this guide does not prove

- It does not prove live model quality, evaluator validity, or production
  readiness.
- It does not replace an organization's security, privacy, legal, or incident
  response process.
- It does not authorize access to private data or external systems.
- It does not make an incomplete evaluation safe to use.
- It does not turn a repaired synthetic result into a production guarantee.

## Related guides

- [AI Incident Response](AI_INCIDENT_RESPONSE.md)
- [Production AI Engineering Bridge](PRODUCTION_AI_ENGINEERING_BRIDGE.md)
- [Agent Evaluation Checklist](../AGENT_EVALUATION_CHECKLIST.md)
- [Production AI Agent Readiness Checklist](PRODUCTION_AI_AGENT_READINESS_CHECKLIST.md)
