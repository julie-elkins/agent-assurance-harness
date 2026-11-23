# Muse Ember Evidence Gate

This is the hackathon-facing path for the Agent Assurance Harness. It demonstrates an
evidence gate: a rule that accepts an agent claim only when the required observable
evidence is present, and blocks or reports a finding when that evidence is missing.

The demo is synthetic and metadata-only. It does not run commands, write to a
repository, use private or certification content, or retain provider text.

## Offline proof

Run the deterministic path first:

```bash
uv run python tools/muse_ember_evidence_gate_demo.py --markdown
```

It checks the built-in scenarios, confirms the guarded reference path passes, and
confirms that deliberately unsafe or weakened evaluator paths are caught. This is the
repeatable proof; it does not depend on network availability or model behavior.

## Optional Muse Ember run

Muse Ember is reached through Meta's Model API Responses endpoint. The local adapter
uses the official endpoint, the `MODEL_API_KEY` environment variable, and the model
identifier `muse-ember-1.0` by default. It sends only built-in synthetic identifiers
and translates the returned structured events into the harness's shared evidence
contract.

Set the credential in the local process, then run exactly one bounded synthetic
scenario:

```bash
export MODEL_API_KEY='set-this-in-your-local-shell'
uv run python tools/muse_ember_evidence_gate_demo.py \
  --live \
  --allow-network \
  --scenario-id unauthorized-side-effect \
  --model muse-ember-1.0 \
  --max-requests 1 \
  --max-output-tokens 128 \
  --max-elapsed-seconds 30 \
  --max-estimated-cost-usd 0.10 \
  --estimated-cost-usd-per-request 0.05 \
  --markdown
```

The request is opt-in, has no retry loop, and is refused unless all ceilings are
explicit. The adapter requests minimal reasoning because this is a short
classification task, sets `store: false`, and uses the output-token ceiling as a
hard local bound. The report includes only the scenario identifier, result statuses,
safe refusal messages, and usage metadata. It never prints the credential, prompt,
response body, or model text.

The live result is an external-validity check: it shows that the provider-facing
adapter can cross the reviewed boundary. The offline result remains the primary
assurance proof because a live model response is not deterministic.

## Three-minute walkthrough

1. Run the offline command and point out the passing guarded path.
2. Point out that the unsafe control and evaluator mutations are caught.
3. Explain that the evidence contract is the decision boundary: plausible output
   alone is not enough.
4. If a credential is available, run the one bounded Muse Ember scenario.
5. Show that the live provider is translated into the same evidence contract and
   the output remains metadata-only.

## What this does not prove

This demo does not prove production safety, live-model quality, deployment health,
provider availability, or correctness outside the built-in synthetic scenarios.
Those limits are explicit because an honest boundary is part of the winning demo.
