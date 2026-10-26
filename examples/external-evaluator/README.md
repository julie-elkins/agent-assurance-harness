# External evaluator import example

These fixtures represent the bounded metadata an external evaluator might export.
They are not copied Inspect or Petri traces. The adapter accepts only source identity,
case identifiers, labels, flags, and revision metadata.

Run the Inspect-shaped fixture:

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

The Petri-shaped fixture uses the same contract:

```bash
uv run python tools/import_external_evaluator.py \
  --input examples/external-evaluator/petri-result.json \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --output /tmp/petri-evaluator-import.json \
  --safety-case-output /tmp/petri-evaluator-safety-case.json \
  --fail-on-review
```

The adapter refuses unsupported fields and blocks a result bound to the wrong
manifest or harness revision. A changed current revision becomes `review_required`
through the canonical reauthorization layer.
