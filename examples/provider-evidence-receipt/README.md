# Provider evidence receipt demo

This demo runs the existing credential-free OpenAI- and Anthropic-shaped adapters
through the same synthetic scenario, then binds both results to the evidence
registry.

```bash
uv run python tools/provider_evidence_receipt.py \
  --provider all \
  --scenario-id tool-misuse \
  --evidence-id run-synthetic-001 \
  --registry examples/change-impact/evidence-registry.json \
  --markdown \
  --fail-on-refusal
```

The output contains provider IDs, model IDs, scenario IDs, event counts, usage
metadata, registry digests, named rerun checks, and statuses. It does not contain
prompts, tool arguments, model output, credentials, or hidden reasoning.

The adapters are synthetic and offline. The receipt proves that both provider-shaped
results crossed the shared metadata contract; it does not prove live provider quality.
