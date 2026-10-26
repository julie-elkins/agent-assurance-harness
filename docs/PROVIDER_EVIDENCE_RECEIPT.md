# Provider evidence receipt

## What this adds

The provider layer already translates OpenAI- and Anthropic-shaped responses into
the shared adapter contract. A provider evidence receipt is the next boundary: it
summarizes that translated run and binds it to one registered evidence result.

The receipt contains:

- provider, model, agent, scenario, and harness identifiers;
- evidence ID and decision target;
- registry-entry digest;
- dependency scope, named rerun checks, and owner;
- event and tool-call counts;
- transport and semantic status;
- bounded usage and refusal metadata;
- receipt digest.

It does not contain prompts, tool arguments, model output, hidden reasoning,
credentials, or raw provider payloads.

## Run the synthetic demonstration

```bash
uv run python tools/provider_evidence_receipt.py \
  --provider all \
  --scenario-id tool-misuse \
  --evidence-id run-synthetic-001 \
  --registry examples/change-impact/evidence-registry.json \
  --revisions examples/change-impact/baseline-revisions.json \
  --markdown \
  --fail-on-refusal
```

Both provider-shaped adapters produce the same receipt contract. The result is
synthetic and offline; it demonstrates the metadata boundary and registry binding,
not live provider quality or production safety.

## Why the receipt is separate

The provider adapter translates a provider response. The evidence registry defines
what a result supports and what should be rerun after a change. The receipt connects
those contracts without making either provider's response format the public evidence
format.

The receipt is an artifact, not an approval. A trusted workflow must still run the
registered checks and record a reauthorization decision.

## Use the receipt in change-impact planning

Generate a receipt against the baseline revisions, then compare it with the current
revision map:

```bash
uv run python tools/provider_evidence_receipt.py \
  --provider all \
  --scenario-id tool-misuse \
  --evidence-id run-synthetic-001 \
  --registry examples/change-impact/evidence-registry.json \
  --revisions examples/change-impact/baseline-revisions.json \
  --output /tmp/provider-evidence-receipt.json \
  --fail-on-refusal

uv run python tools/agent_impact_plan.py \
  --baseline-revisions examples/change-impact/baseline-revisions.json \
  --current-revisions examples/change-impact/current-revisions.json \
  --manifest examples/run-manifest/manifest.json \
  --registry examples/change-impact/evidence-registry.json \
  --receipt /tmp/provider-evidence-receipt.json \
  --markdown \
  --fail-on-rerun
```

The second command reports `rerun_required` because the current policy revision
changed. It also reports which provider receipts were accepted before the change and
which registered checks must run next.
