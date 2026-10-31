# Agent evaluation checklist

This checklist is the operational companion to the
[Agent Evaluation and Release guide](https://github.com/julie-elkins/agent-systems-design-guide/blob/main/AGENT_EVALUATION_AND_RELEASE.md).
It helps a reviewer determine whether an evaluation result can support a declared
decision.

It is not production approval, a certification, a security sign-off, or a universal
scoring formula. A completed row means that evidence was reviewed for the declared
workflow and revision. It does not prove behavior outside that scope.

## How to use it

Complete every applicable row. Use these statuses:

- `observed`: the required evidence was found and matched the declared workflow;
- `missing`: evidence was expected but was not found;
- `refused`: a control declined to proceed because required input or authority was unsafe;
- `failed`: the evidence was present but the declared rule was not met;
- `not_evaluated`: the evidence was unavailable or invalid; and
- `not_applicable`: the row does not apply to this workflow.

`not_evaluated` is not `passed`. If a row is missing or not evaluated, record the
owner, the next action, and whether the release decision is blocked.

Each row requires four things:

1. an owner;
2. an evidence artifact or identifier;
3. a threshold or decision rule; and
4. a defined action when evidence is missing.

## 1. Decision and requirements

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | User task and decision |  | Task contract and workflow revision | The task and decision affected by the agent are explicit. | Hold the evaluation; do not choose a score without a declared target. |
|  | Failure cost |  | Risk statement and high-risk slices | The most expensive plausible failure is named. | Escalate to the accountable product or risk owner. |
|  | Allowed sources and actions |  | Source, tool, authorization, and confirmation contract | Permitted sources and actions are bounded. | Block release evidence until the boundary is defined. |
|  | Terminal outcomes |  | Completion, refusal, escalation, and unavailable-state definitions | The workflow distinguishes success from refusal, failure, and not evaluated. | Add the missing state before interpreting results. |

## 2. Test cases and golden dataset

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Representative coverage |  | Versioned case manifest and coverage summary | Normal, boundary, missing, conflicting, unauthorized, and failure cases are included. | Mark coverage incomplete and block any claim that the set is representative. |
|  | Expected outcomes |  | Reviewed expected answers, actions, refusals, or acceptable ranges | Each case has a declared reference and review provenance. | Do not treat an unreviewed expected result as ground truth. |
|  | Negative controls |  | Deliberately degraded case and expected block | The evaluator catches at least one known false-pass condition. | Block the gate until the control is restored. |
|  | Versioning and separation |  | Dataset, calibration, held-out, source, and revision identifiers | Calibration cases are separate from held-out measurement cases. | Report the result as not established. |
|  | Failure-to-test loop |  | Reviewed failure category and new regression case | Important real failures become cases or have a documented reason not to. | Assign an owner and preserve the unresolved gap. |

## 3. Deterministic evaluation

Deterministic checks are fixed-rule checks that should produce the same result for the
same observed evidence.

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Result correctness |  | Expected-versus-observed comparison | Exact, numeric, schema, or bounded-answer rule is met. | Mark the case not evaluated. |
|  | Tool selection and arguments |  | Identifier-only tool trace and schema result | The permitted tool and valid arguments were used. | Treat the action as unverified; do not infer correctness from the final text. |
|  | Authorization and confirmation |  | Authorization decision and confirmation state | Required authority and confirmation occurred before the action. | Block the action or release decision. |
|  | State change |  | Synthetic state before/after record | The declared state transition occurred and was confirmed. | Keep the task incomplete. |
|  | Latency, cost, and stop condition |  | Bounded usage and timing metadata | Declared ceilings were respected. | Mark the run failed or unavailable according to policy. |

## 4. Semantic evaluation

Semantic checks judge meaning and evidentiary support rather than exact text identity.

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Groundedness |  | Approved-source identifiers and support assessment | Claims are supported by permitted, current evidence. | Require abstention or human review. |
|  | Relevance |  | Rubric result and reviewed examples | The response addresses the declared user task. | Separate irrelevance from factual correctness. |
|  | Unsupported claims |  | Claim-level finding or negative control | Fabricated or unsupported claims are caught. | Do not report a clean result. |
|  | Grader validity |  | Human reference, agreement result, disagreement review | The automated judge has a documented calibration result and limitation. | Treat its score as exploratory only. |
|  | Evaluator layers |  | Trace-linked evaluator report and human review record | Deterministic checks cover schemas, tool calls, authorization, required evidence, latency, and cost; semantic or agent-based grading is calibrated or abstains. | Keep the result `not_evaluated`; do not collapse missing evidence into a score. |

## 5. Behavioral, multi-turn, and trajectory evaluation

Behavioral checks inspect what the agent does over an interaction. A trajectory is the
sequence of planning, tool calls, intermediate state, retries, and recovery decisions.

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Task completion |  | End-state evidence and semantic outcome | The user task reached the declared safe terminal state. | Keep transport success separate from task success. |
|  | Multi-turn state |  | Conversation case, turn state, and terminal outcome | Required constraints persist; forbidden state does not leak; final state is correct. | Mark conversation-level behavior not evaluated. |
|  | Trajectory validity |  | Ordered tool and decision trace | The path used allowed tools, arguments, sources, and dependencies. | Do not let a plausible final answer erase the path failure. |
|  | Recovery and abstention |  | Tool/source failure case and observed response | The agent retries safely, asks for clarification, refuses, or escalates as declared. | Block the affected failure class. |
|  | Consistency |  | Repeated-run manifest and result distribution | Variation is within the declared risk-specific tolerance. | Report the comparison as inconclusive. |
|  | Safety and prompt injection |  | Synthetic adversarial cases and blocked results | Unauthorized instructions and harmful requests do not bypass the boundary. | Hold the relevant release path. |

## 6. Trace and observability

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Trace completeness |  | Trace schema and completeness report | Required task, revision, tool, state, outcome, and evaluator fields exist. | Report not evaluated; absent evidence is not a pass. |
|  | Revision binding |  | Model, prompt, tool, data, policy, harness, and grader revisions | The result is bound to the exact system under review. | Require a rerun or reauthorization. |
|  | Privacy boundary |  | Output scan and data-classification decision | Shared artifacts contain only permitted metadata or approved content. | Remove or quarantine the artifact. |
|  | Status visibility |  | Counts for completed, skipped, refused, failed, and unavailable checks | The report cannot silently omit checks that did not run. | Block the report from release use. |

## 7. Metrics, baselines, and uncertainty

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Baseline comparison |  | Same-case baseline/current report | The comparison uses the same declared cases and conditions. | Do not call the change an improvement. |
|  | Sample size and uncertainty |  | Counts, intervals, or variance summary | The result is large or stable enough for the decision being made. | Report inconclusive and identify the next sample or rerun. |
|  | High-risk slices |  | Slice-level results by risk, tool, source, or task | A favorable average cannot hide a blocking high-risk failure. | Hold the affected slice. |
|  | Repeated-run variation |  | Null-run or repeated-sampling report | Observed movement exceeds the declared evaluation noise or is labeled uncertain. | Withdraw the headline comparison. |
|  | Metric tradeoffs |  | Accuracy, safety, latency, cost, and user-outcome comparison | A higher-priority regression cannot be hidden by a lower-priority gain. | Escalate the tradeoff to the decision owner. |
|  | Controlled variant comparison |  | Baseline/candidate report with separate dimensions | Correctness, safety, tool-call correctness, latency, cost, and user outcomes are reported separately; blocking thresholds and the rerun policy were written before interpretation. | Mark the comparison inconclusive and do not select a variant from the headline score. |

## 8. Release and change management

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Release contract |  | Blocking and informative thresholds | Blocking checks and non-blocking observations are explicit before results are read. | Do not infer the release rule from the score. |
|  | Change impact |  | Changed revisions and rerun plan | Relevant model, prompt, tool, policy, data, or evaluator changes trigger review. | Mark prior evidence stale or require reauthorization. |
|  | Human decision |  | Approval, hold, rollback, or residual-risk record | A named accountable person owns the final decision. | Keep the workflow on hold. |
|  | Rollback or containment |  | Reversal plan and verification result | The team can narrow, stop, or reverse the changed behavior. | Do not broaden the release. |

## 9. Monitoring and feedback

| Status | Check | Owner | Evidence artifact | Threshold or decision rule | If evidence is missing |
| --- | --- | --- | --- | --- | --- |
|  | Production feedback |  | Safe failure signal and reviewed category | Real failures can become reviewed evaluation cases. | Record the gap and assign an owner. |
|  | User and business outcomes |  | Time to useful answer, rework, escalation, completion, and incorrect-action rates | Outcomes are interpreted alongside correctness, safety, and grounding. | Do not claim product improvement from model metrics alone. |
|  | Drift and freshness |  | Source freshness, case drift, and regression report | Stale data or changed usage triggers evaluation review. | Narrow or pause the affected claim. |
|  | Limitations |  | Claim-boundary statement | Reports state what the evidence does not prove. | Treat the result as incomplete. |

## What this checklist does not prove

- It does not prove live model quality, production safety, security approval, or
  business impact.
- It does not replace human approval, incident response, privacy review, or change policy.
- It does not authorize external actions or access to private data.
- It does not make an automated judge ground truth.
