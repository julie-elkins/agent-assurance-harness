# Phase 4 research design

## Purpose

Phase 4 expands the agent-reauthorization study beyond the original 18-case pilot
and 12-case compound robustness extension. Its purpose is to test whether the
observed decision differences persist across a larger, varied synthetic matrix
without changing the research question.

The study asks:

> Can revision-aware evidence plus explicit reauthorization reduce unsupported
> release decisions after a tool-using agent workflow changes?

It does not ask whether a named model is safe, whether the protocol works in
production, or whether the synthetic reference decisions are universally correct.

## Design

Phase 4 contains 210 new cases:

- 180 base cases: six change families × three variants × ten cases per cell.
- 30 compound-change cases: five per family, held out from development.

The six families are prompt, tool, retrieval, authorization, evaluator, and
deployment changes. The three base variants are current, reevaluation required,
and negative control.

Each case has a stable identifier, revision lineage, changed-component descriptor,
evidence revision, case index, template identifier, split, and independence group.
These fields make the case construction auditable without exposing prompts,
provider output, tool payloads, or private telemetry.

## Splits

The base matrix is divided before evaluation:

| split | cases | purpose |
| --- | ---: | --- |
| development | 72 | exercise the implementation and check protocol wiring |
| robustness | 54 | test repeated family/variant coverage outside development |
| locked holdout | 54 | evaluate the frozen protocol after development work |
| locked compound holdout | 30 | test combined family-plus-deployment changes |

The current implementation is deterministic. It does not tune thresholds on the
holdout and does not use a provider API.

## Conditions

Every case is evaluated under the same three conditions:

1. pass/fail reporting;
2. revision-aware evidence; and
3. revision-aware evidence plus reauthorization controls.

The same case is therefore a blocked-design comparison: the case does not change
between conditions, only the decision process does.

## Reference decisions

The checked-in Phase-4 manifest is separate from the evaluator. It maps explicit
case-ID patterns to `reauthorized`, `review_required`, or `blocked`. The report
records the manifest digest and verifies exact case-ID coverage.

This separation reduces implementation coupling. It does not make the reference
decision a universal truth; it makes disagreement with a declared study oracle
measurable.

## Analysis

The primary outcome is false-ready approval: a reauthorized decision when the
reference decision is `review_required` or `blocked`.

Secondary outcomes are stale-claim detection, correct escalation, detection
latency, evaluation runs, review steps, and bounded synthetic time units.

Phase 4 reports exact counts and proportions. It does not use inferential
statistics because deterministic synthetic cases are not a random sample from a
population. A later empirical phase should use real or human-reviewed cases,
pre-registered sampling, and an analysis plan appropriate to those observations.

## Planned external-validity phase

The next study layer should run the same protocol against a bounded agent system
with:

- an actual language model or a deterministic model substitute;
- tool calls and recorded traces;
- an independent evaluator;
- controlled changes to prompts, tools, retrieval, authorization, evaluators,
  and deployment configuration;
- a cost and latency ceiling; and
- a locked scenario set.

That phase tests whether the protocol survives model and tool behavior. It is not
needed to validate the arithmetic and control logic in this offline Phase 4 run,
but it is needed before making claims about real-system usefulness.

## Reproduction

Run from the repository root:

```bash
.venv/bin/python tools/reauthorization_pilot.py \
  --phase4 \
  --markdown \
  --fail-on-findings
```

The command emits identifiers, statuses, counts, and hashes only.
