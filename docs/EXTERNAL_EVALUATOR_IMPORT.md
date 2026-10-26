# External evaluator import

The external evaluator adapter accepts bounded results shaped like Inspect, Petri, or a
local evaluator and converts them into the existing Monitorability Workbench contract.

An adapter here means a strict translator at the boundary. It does not run the external
system, install its SDK, or copy its trace. It accepts only case identifiers, labels,
monitor and evaluator flags, source identity, and revision metadata.

## Run an Inspect-shaped result

```bash
uv run python tools/import_external_evaluator.py \
  --input examples/external-evaluator/inspect-result.json \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --output /tmp/external-evaluator-import.json \
  --safety-case-output /tmp/external-evaluator-safety-case.json \
  --markdown \
  --fail-on-review
```

Run the Petri-shaped fixture by replacing the input path:

```bash
uv run python tools/import_external_evaluator.py \
  --input examples/external-evaluator/petri-result.json \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --output /tmp/petri-evaluator-import.json \
  --safety-case-output /tmp/petri-evaluator-safety-case.json \
  --fail-on-review
```

The output can be passed to the Evidence Validity Explorer using the imported
`monitorability_report` and `safety_case` objects. A changed current revision produces
`review_required`; a result bound to the wrong manifest or harness revision is blocked
before scoring.

## Deliberate limits

The public repository contains synthetic fixtures only. The adapter does not fetch
Inspect or Petri data, call provider APIs, accept raw traces, or infer labels from
content. Source-system identity does not prove the external evaluator is valid; the
imported labels and flags still go through the local calibration and held-out controls.
