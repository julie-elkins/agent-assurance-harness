# Teaching and adoption evidence

This guide connects the harness controls to technical enablement. The
[AI Teaching Strategies](https://github.com/julie-elkins/ai-teaching-strategies)
repository owns the reusable teaching cards; this repository owns the runnable
synthetic controls and metadata-only evidence.

## Recommended teaching loop

1. Declare the learner audience and the decision the lesson supports.
2. Run a positive synthetic path.
3. Run a deliberately degraded path that the control must catch.
4. Ask the learner to identify the evidence, terminal state, limitation, and
   next action.
5. Calibrate facilitators against the same observer rubric.
6. Use bounded learner artifacts or repeated practice only when deciding what
   to revise.

## Evidence boundaries

The harness can show that a declared control emitted the expected status,
identifier, count, hash, or blocking result. It cannot prove that a learner
understood every concept, that a course caused a later behavior, or that a
synthetic control is sufficient for a live production system.

Keep the following separate:

- **delivery evidence:** the lesson, lab, rubric, or feedback step was provided;
- **learner evidence:** the learner produced or explained the target artifact;
- **system evidence:** the harness control observed the declared workflow state; and
- **adoption evidence:** a bounded, consented signal informed a revision decision.

Views, completions, and positive comments can guide topic selection. They are
not substitutes for learner or system evidence.

## Public boundary

Use synthetic fixtures and metadata-only reports. Do not add learner records,
raw traces, prompts, credentials, private provider output, or internal project
identifiers to this repository.
