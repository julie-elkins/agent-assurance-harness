# Evidence Validity Explorer

The Evidence Validity Explorer is a local static HTML view of one run manifest
evaluated against two revision snapshots:

1. the current snapshot, where the recorded evidence should remain
   `reauthorized`; and
2. a deliberately changed snapshot, where the same evidence should become
   `reauthorization_required`.

This makes the central control visible: evidence that was successful for one model,
prompt, tool, policy, data, repository, environment, and grader revision is not
silently reusable after one of those dependencies changes.

The explorer is a presentation layer over the existing
`agent_reliability_lab.run_manifest.evaluate_reauthorization` function. It does not
rerun an agent, call OpenAI or Anthropic, read credentials, or store prompts, tool
payloads, provider output, or private paths.

## Generate the local page

From the repository root:

```bash
Generate the synthetic provider receipt first:

```bash
uv run python tools/provider_evidence_receipt.py \
  --provider all \
  --evidence-id run-synthetic-001 \
  --registry examples/change-impact/evidence-registry.json \
  --revisions examples/run-manifest/current-revisions.json \
  --output /tmp/agent-provider-evidence-receipt.json \
  --fail-on-refusal
```

Then render the explorer:

```bash
uv run python tools/evidence_validity_explorer.py \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --changed-revisions examples/change-impact/current-revisions.json \
  --provenance examples/run-manifest/evidence-provenance.json \
  --missing-provenance examples/run-manifest/evidence-provenance-missing.json \
  --registry examples/change-impact/evidence-registry.json \
  --receipt /tmp/agent-provider-evidence-receipt.json \
  --output /tmp/agent-evidence-validity-explorer.html
```

Open `/tmp/agent-evidence-validity-explorer.html` in a browser. For a shareable
demonstration, use the four-step assurance story and provider receipt lane or take one
screenshot that includes the observed, changed, reauthorization-required, and
missing-evidence states. The provider lane also shows accepted OpenAI and Anthropic
receipts, the named checks and owner, the policy-change `rerun_required` decision, and a
stale-receipt negative control that is blocked before reuse. The page also shows the
safe receipt, grader-validity, and synthetic deployment metadata. It is self-contained
and has no external JavaScript, CSS, image, authentication, or telemetry dependency.

## What a reviewer can see

- the declared decision target and current evidence status;
- the changed dependency count and names;
- the exact current, recorded, and changed revision identifiers;
- repeat count, bounded request budget, and evidence expiration;
- the required action after a revision change; and
- the four-step story from observed evidence to blocked reuse; and
- the accepted provider receipts, named rerun checks, owner, and impact decision;
- the deliberately stale receipt that is blocked by a revision mismatch; and
- receipt, grader-validity, and synthetic deployment-context identifiers;
- the boundary between what the manifest decision proves and what it does not prove.

The page uses color only as a secondary signal. The status text remains explicit so
the decision is still understandable in grayscale, by screen reader, or when viewed
in a screenshot.

## Deliberate limits

This is not a hosted observability dashboard, model-quality leaderboard, or production
approval system. It shows one bounded metadata decision and its synthetic negative
control. A `reauthorized` result means the evidence still matches the declared
revision snapshot; it does not mean that a human approved the next action or that the
underlying agent is safe in every environment. It does not create signed attestations;
that identity and key-management boundary is future work.
