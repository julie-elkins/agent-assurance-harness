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
uv run python tools/evidence_validity_explorer.py \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --changed-revisions examples/run-manifest/changed-revisions.json \
  --output /tmp/agent-evidence-validity-explorer.html
```

Open `/tmp/agent-evidence-validity-explorer.html` in a browser. For a shareable
demonstration, use the page's current and changed panels or take one screenshot that
includes both decisions. The page is self-contained and has no external JavaScript,
CSS, image, authentication, or telemetry dependency.

## What a reviewer can see

- the declared decision target and current evidence status;
- the changed dependency count and names;
- the exact current, recorded, and changed revision identifiers;
- repeat count, bounded request budget, and evidence expiration;
- the required action after a revision change; and
- the boundary between what the manifest decision proves and what it does not prove.

The page uses color only as a secondary signal. The status text remains explicit so
the decision is still understandable in grayscale, by screen reader, or when viewed
in a screenshot.

## Deliberate limits

This is not a hosted observability dashboard, model-quality leaderboard, or production
approval system. It shows one bounded metadata decision and its synthetic negative
control. A `reauthorized` result means the evidence still matches the declared
revision snapshot; it does not mean that a human approved the next action or that the
underlying agent is safe in every environment.
