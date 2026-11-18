# Provider shadow reauthorization

This integration connects the synthetic shadow-execution receipt to the
provider-neutral run manifest. A run manifest is the metadata record that binds
an evidence result to the model, harness, policy, tool, data, environment, and
grader revisions that produced it.

The integration uses the same action contract for OpenAI-shaped and
Anthropic-shaped proposals. The provider-shaped lane changes only synthetic
provider, model, agent, and run identifiers; it does not contain provider
requests, responses, prompts, credentials, or transcripts.

## Run the demonstration

From the repository root:

```bash
uv run python tools/shadow_reauthorization_demo.py \
  --markdown \
  --fail-on-findings
```

The demo evaluates both provider lanes twice:

- `current` uses the matching revision map and should return `reauthorized`;
- `changed` changes the prompt and tool revisions and should return
  `reauthorization_required`.

The changed result is not a failure in this demonstration. It is the expected
negative control: the prior shadow receipt must not be reused silently after a
declared dependency changes.

## Decision precedence

The final status combines two independent checks:

1. the shadow receipt says whether the proposed effect was allowed, blocked, or
   sent to human review;
2. the existing run-manifest evaluator says whether the evidence remains valid
   for the current revision map.

The integration uses this precedence:

1. `blocked`;
2. `human_review`;
3. `reauthorization_required`;
4. `reauthorized`.

This prevents a current manifest from making a blocked or human-review action
look reusable.

The binding also checks that:

- the provider, model, and agent identifiers agree with the manifest;
- the proposed tool is within the manifest's tool scope; and
- the action policy revision matches the manifest policy revision.

## What this proves

The synthetic integration demonstrates that:

- OpenAI- and Anthropic-shaped proposals can share one action contract;
- a matched shadow effect can remain reusable while revisions are unchanged;
- a prompt or tool revision forces reauthorization for both provider lanes; and
- shadow receipts remain separate from provider content.

## What this does not prove

It does not prove live provider behaviour, provider quality, real-tool safety,
operating-system isolation, rollback, or production reauthorization. The
provider lanes are contract fixtures, not live provider evaluations.
