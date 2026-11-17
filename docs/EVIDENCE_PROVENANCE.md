# Evidence provenance gate

The evidence provenance gate answers a narrow question:

> Did a producer record an evidence artifact for this exact run manifest?

“Provenance” means metadata about where a result came from. The gate checks that
metadata without reading or exporting a trace, transcript, grader result, model
response, prompt, or tool payload.

## Why this is separate from the run manifest

The run manifest describes the conditions a result claims to bind: model, harness,
prompt, tools, policy, data, repository, environment, grader, budget, stop condition,
repeatability, scope, and expiration.

That shape alone does not prove that an evidence artifact was actually observed. The
separate producer record binds to the manifest's canonical digest and records:

- producer identifier;
- evidence artifact digest, if one was observed;
- artifact count;
- observed or missing state; and
- redaction policy identifier;
- receipt metadata such as artifact type, producer version, capture scope, and retention
  status;
- grader-validity metadata such as grader type, calibration state, sample count, and
  independent-breaker identifier; and
- synthetic deployment context such as scenario source, trajectory horizon, tool-risk
  tier, and coverage profile.

Keeping the record separate preserves the v1 manifest contract for existing consumers
and makes the missing-artifact negative control explicit.

## Decisions

| Status | Meaning | Reuse |
| --- | --- | --- |
| `evidence_observed` | A valid producer record is bound to this manifest and reports at least one observed artifact. | The provenance check supports reuse; other gates still apply. |
| `evidence_missing` | The record is valid but reports no observed artifact. | Do not reuse the result until evidence is collected. |
| `blocked` | The record is invalid or bound to a different manifest. | Repair or regenerate the record before reuse. |

This is not a cryptographic signature, a semantic quality judgment, or proof that a
provider response was correct. Those require separately approved evidence and evaluation
layers.

## Evidence custody and authorization

Evidence custody means identifying who holds the record used to support a decision
and whether the executor could rewrite or delete it. For a consequential action,
record the authorization owner separately from the agent or tool that performed the
action. If the executor controls the only copy of the evidence, treat that record
as weaker than independently held evidence and keep the result bounded or
`not_evaluated`.

The public harness records only synthetic identifiers and states. It does not claim
that a real evidence store is append-only, immutable, or independently operated.
Those properties require system-specific controls and verification.

## What remains out of scope

The current record is a validated metadata receipt, not a signed attestation. A signed
attestation is a cryptographically verifiable statement that a trusted producer created
the record. Adding one requires an identity, key storage, rotation, revocation, and
append-only retention design, so it is a future phase rather than a hidden claim of the
current public build.

The deployment-context values in the public fixtures are synthetic. They demonstrate the
shape of the contract without importing incident data, private traces, provider output,
or internal evaluation material.

## Run the public synthetic demo

The positive fixture is synthetic and metadata-only:

```bash
uv run python tools/evidence_provenance_gate.py \
  --manifest examples/run-manifest/manifest.json \
  --provenance examples/run-manifest/evidence-provenance.json \
  --markdown \
  --fail-on-missing
```

The expected decision is `EVIDENCE_OBSERVED` with exit code `0`.

The negative control deliberately reports no observed artifact:

```bash
uv run python tools/evidence_provenance_gate.py \
  --manifest examples/run-manifest/manifest.json \
  --provenance examples/run-manifest/evidence-provenance-missing.json \
  --markdown \
  --fail-on-missing
```

The expected decision is `EVIDENCE_MISSING` with exit code `1`. That failure is the
important result: a successful-looking manifest cannot be reused when its producer did
not record evidence.
