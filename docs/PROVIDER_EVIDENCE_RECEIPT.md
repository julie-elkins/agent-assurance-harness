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
