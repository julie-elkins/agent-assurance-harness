# Human reauthorization record

## What this adds

The bounded rerun executor answers: “Did the selected synthetic checks complete,
and did they catch their known negative controls?”

This record answers a different question: “Has an accountable person decided
that this exact evidence may be reused for this exact decision target?”

The validator keeps those questions separate. A passing rerun never creates a
human decision automatically.

## Run the positive example

```bash
uv run python tools/reauthorization_record.py \
  --record examples/reauthorization-record/record.json \
  --rerun-result examples/reauthorization-record/rerun-result.json \
  --now 2026-11-10T12:00:00Z \
  --markdown \
  --fail-on-nonreusable
```

The example returns `reauthorized` because:

- the rerun completed;
- the evidence ID and decision target match;
- the baseline and current revision digests match;
- the selected check IDs match;
- the rerun result digest matches; and
- the record has not expired.

The `--now` option makes demonstrations and tests deterministic. In normal use,
the validator uses the current UTC time.

## Run the CI contract

The dedicated [evidence reauthorization workflow](../.github/workflows/reauthorization.yml)
connects the three boundaries in order:

1. generate a synthetic change-impact plan;
2. run the bounded offline checks selected by that plan; and
3. validate the checked-in human reauthorization record against its exact rerun
   result.

The workflow fails if the rerun does not complete or the reauthorization is not
currently reusable. It uploads the plan, rerun, and validation reports as
metadata-only artifacts—identifiers, states, hashes, counts, and reason codes,
not prompts, traces, credentials, or provider output—even when a later step
fails. The workflow has read-only repository permissions and does not write a
decision record, deployment state, or release approval.

The checked-in record is an expiring synthetic contract fixture. CI validates its
real expiration against the current UTC time, so the workflow is expected to
require a reviewed fixture update after `expires_at`. That expiration is
deliberate: a stale example must become visible instead of remaining green
forever. This workflow validates the assurance boundary; it is not deployment
approval and does not prove production safety or live model quality.

## Record contract

The record is a separate JSON artifact defined by
[the versioned schema](../schemas/reauthorization-record-v1.json). It includes:

- the human decision: `reauthorized`, `held`, or `blocked`;
- the accountable owner and person who made the decision;
- the decision target and evidence IDs;
- the exact baseline/current revision digests;
- the executor version and selected check IDs;
- the canonical digest of the complete rerun result;
- the decision and expiration timestamps;
- residual risk; and
- the next action.

The record is intentionally not written into the rerun result. Keeping the
artifacts separate preserves the distinction between observed execution and
human authority.

## Validation outcomes

- `reauthorized`: the record is currently reusable for its exact decision target
  and evidence scope;
- `held`: a human has intentionally paused reuse;
- `blocked`: a control, binding, or decision prevents reuse;
- `expired`: a previously reauthorized record is past its expiration; and
- `refused`: the input artifact is malformed or outside the contract.

The validator fails closed (invalid or missing evidence blocks reuse). It also
rejects changed revision digests, changed evidence IDs, changed check lists,
failed reruns, missing owners, future decision timestamps, and expired records.

## What this does not do

This workflow does not approve deployment, prove production safety, establish
live model quality, call OpenAI or Anthropic, access credentials, make network
requests, or export prompts, traces, tool payloads, or provider output. A later
CI workflow may consume the validator, but CI must preserve the same human
decision boundary.
