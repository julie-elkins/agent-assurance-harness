# Review workflow assurance

This workflow connects a private domain-review system to the public Agent
Assurance Harness without exporting the domain content.

An **adapter** is a small connector that translates one system's result into a
declared contract. Here, the adapter emits a metadata-only manifest. The
harness checks workflow completeness and evidence integrity; it does not judge
the underlying subject matter.

## Boundary

The private review system keeps:

- source content;
- answer keys or expected answers;
- reviewer identities;
- prompts and rationales;
- raw tool arguments and tool results;
- private traces and local paths.

The manifest may contain only:

- run and workflow identifiers;
- a source revision digest;
- expected stage names and status values;
- counts;
- refusal reason codes;
- evidence counts and status;
- artifact digests;
- bounded resource usage and limits.

The required `human_decision` value is `required`, and the harness always
returns `release_authorized: false`. A successful result means only
`pass_for_human_review`: an authorized person must still make the domain and
release decision.

## Reference flow

```text
private item review
  -> metadata-only manifest
  -> review_workflow_assurance_report.py
  -> pass_for_human_review | blocked
  -> private review report
  -> authorized human decision
```

Run the validator locally:

```text
uv run python tools/review_workflow_assurance_report.py \
  --manifest /path/to/private/review-workflow-assurance.json \
  --markdown \
  --fail-on-blocked
```

The manifest contract is
[review-workflow-assurance-v1.json](../schemas/review-workflow-assurance-v1.json).
The validator is intentionally provider-neutral and offline. It does not call
an LLM, fetch a repository, or upload the manifest.

## What the result proves

`pass_for_human_review` proves that the declared stages completed, refusal
codes are absent, required evidence is present, counts reconcile, and resource
limits were respected.

It does not prove that the item review is technically correct, fair, valid,
or ready for publication. Those remain private domain judgments and human
decisions.
