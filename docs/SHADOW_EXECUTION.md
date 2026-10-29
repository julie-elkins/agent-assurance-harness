# Shadow execution boundary

Shadow execution is a rehearsal of a proposed side effect before the real tool
would be called. A side effect is an external change such as a repository update,
deployment, message, or record write. The first version in this repository is
synthetic: it compares identifier-only intended and observed effects and never
invokes a real tool.

## What it answers

The demo answers:

> What did the agent intend to change, what did the safe rehearsal observe, and
> should the action be allowed, blocked, or reviewed by a person?

It produces three decisions:

- `allow` — authority was present and the intended and observed synthetic effects
  matched.
- `block` — required execution authority was missing or revoked. The simulator
  does not run in this case.
- `human_review` — the effects differed, the resulting state was ambiguous, or
  policy requires a human decision.

## Run the demo

From the repository root:

```bash
uv run python tools/shadow_execution_demo.py \
  --manifest examples/shadow-execution/manifest.json \
  --markdown \
  --fail-on-block
```

The fixture contains five synthetic controls:

1. a matched effect that can be allowed;
2. missing authority that blocks before simulation;
3. an observed effect mismatch that requires review;
4. an action that requires human approval; and
5. an ambiguous effect state that requires review.

The `--fail-on-block` option means the command fails if the declared controls do
not produce their expected decisions. It does not mean that the expected
negative-control case must be removed.

## What the receipt contains

The receipt binds:

- action and operation identifiers;
- tool and effect-class identifiers;
- policy revision;
- intended and observed effect digests;
- authority-check ordering;
- whether the synthetic simulation ran;
- whether a real side effect was attempted; and
- stable reason codes.

The digest is a one-way fingerprint of the declared metadata. It is not a
signature, a record of tool arguments, or proof that a live system interpreted an
action correctly.

## What this does not prove

The synthetic boundary does not prove:

- operating-system sandboxing;
- rollback of a real external change;
- that a real tool has no hidden write path;
- provider quality;
- production safety; or
- that a human approved the action.

Those claims require separate security, delivery-path, and deployment reviews.
The first milestone deliberately proves less so that a reviewer can see exactly
which control ran and which evidence is still missing.
