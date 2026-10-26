# Monitorability and Evaluator Validity Workbench

The Monitorability Workbench asks whether the system measuring agent safety is itself
reliable enough to support a human safety decision.

Monitorability means whether a safety monitor detects concerning behaviour. Evaluator
validity means whether the grader or judge agrees with the declared synthetic ground
truth. The workbench keeps those measurements separate because a plausible task result
can coexist with a weak safety measurement.

## Run the synthetic path

From the repository root:

```bash
uv run python tools/monitorability_workbench.py \
  --cases examples/monitorability/cases.json \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --decision-target release-agent-v1 \
  --output /tmp/monitorability-report.json \
  --safety-case-output /tmp/monitorability-safety-case.json \
  --negative-control-output /tmp/monitorability-negative-control.json \
  --fail-on-review
```

The command emits calibration metrics, held-out recall, benign-control false-positive
rate, evaluator accuracy, approximate 95% uncertainty intervals, an
evaluation-awareness detection gap, run-manifest reauthorization state, a
metadata-only safety case, and a deliberate held-out monitor-miss negative control.

The labels and cases are synthetic identifiers and booleans. No model, provider SDK,
network, prompt, transcript, tool payload, credential, or private trace is used.

## Add the results to the visual explorer

The existing Evidence Validity Explorer can display the workbench result alongside
provider receipts and revision impact:

```bash
uv run python tools/evidence_validity_explorer.py \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --changed-revisions examples/change-impact/current-revisions.json \
  --monitorability-report /tmp/monitorability-report.json \
  --monitorability-negative-control /tmp/monitorability-negative-control.json \
  --safety-case /tmp/monitorability-safety-case.json \
  --output /tmp/agent-evidence-validity-explorer.html
```

The page shows whether the measurement system is ready for human review, not whether
the agent is safe in general. A changed model, harness, policy, data, environment, or
grader revision can require reauthorization before the result is reused.

## CI gate

The blocking reliability workflow runs the same contract through
`tools/monitorability_ci_gate.py`. It requires the positive report to be
`ready_for_human_review`, the deliberate held-out miss to be `review_required`, and
the changed-revision report to require reauthorization. The workflow uploads the five
metadata-only JSON artifacts for reviewer inspection.

## Deliberate limits

The default thresholds are modelling assumptions for the synthetic demonstration. They
are parameters, not universal safety limits. The Wilson intervals are approximate
uncertainty summaries, not confidence that a production monitor will generalise.

The generated safety case always requires human review. Signed attestations and
cryptographic producer identity remain future work.
