# ATIF evidence conformance

ATIF means Agent Trajectory Interchange Format. In this repository, the ATIF
evidence-conformance lane checks the bounded metadata projection produced by a
local provider or Harbor adapter. It does not publish or parse raw trajectories.

## What it checks

The lane checks whether a summary has:

- a supported ATIF schema identifier;
- an observed trajectory artifact with a digest, positive step count, and
  artifact count;
- complete event linkage when tool calls are reported;
- a terminal status consistent with the observed artifact; and
- the declared `metadata-only-v1` redaction policy.

Task correctness remains a separate dimension. A summary may say that a task
passed, but that value does not make missing evidence acceptable.

## Run the synthetic lane

```bash
uv run python tools/atif_conformance_report.py \
  --summary examples/atif-conformance/positive.json \
  --markdown \
  --fail-on-findings
```

The negative control demonstrates the important boundary:

```bash
uv run python tools/atif_conformance_report.py \
  --summary examples/atif-conformance/missing-artifact.json \
  --fail-on-findings
```

The second command is expected to return non-zero. It proves that a completed
status is not accepted when the expected trajectory artifact is missing.

## Public boundary

The input is intentionally a summary, not an ATIF trajectory. Public fixtures
contain identifiers, counts, statuses, and synthetic digests only. Prompts,
tool arguments, tool results, provider responses, credentials, hidden reasoning,
and raw trajectory content are refused and are never echoed in the report.

This lane does not establish model quality, semantic task correctness, live
provider availability, or production safety. Those claims require separate
checks and explicit evidence.

The current profile accepts `ATIF-v1.2` and `ATIF-v1.5`, matching the versions
handled by the public Harbor adapter. A future profile can add another schema
version after its adapter contract and negative controls are reviewed.

The `harbor-adapter-v1.2.json` fixture is a synthetic copy of the public
receipt-to-summary contract exercised by the Harbor adapter's post-merge smoke.
It contains no raw trajectory or provider data; its purpose is to catch drift
in the shared field names, statuses, counts, digest format, and schema version.

## Muse Ember track

The repository includes a synthetic `muse-ember` fixture to prove that a
provider-specific comparison can reuse the same evidence contract. It is not a
live Muse result and does not claim that a public Ember endpoint is supported.
The live adapter remains deferred until Meta publishes a stable public model
identifier and endpoint contract.
