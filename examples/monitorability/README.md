# Monitorability Workbench example

This fixture is synthetic and identifier-only. It demonstrates the first complete
monitorability path:

- calibration cases establish the declared labels;
- held-out cases measure generalisation beyond calibration;
- benign controls measure false positives;
- paired evaluation-awareness cases measure whether detection changes when a case is
  marked as being evaluated.

Run the workbench from the repository root:

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

The command produces a ready-for-human-review synthetic report and a deliberate
held-out monitor-miss negative control. It does not call a model, network, or provider
SDK. The outputs contain identifiers, labels, counts, rates, revision digests, statuses,
and limitations only.

The safety case is not a deployment approval, signed attestation, or proof of live model
safety. Signed attestations remain future work.
