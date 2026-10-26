# Agent change impact and reauthorization

## What this adds

An evaluation can be accurate for the system it measured and still become stale
after a model, prompt, tool, policy, data, harness, or grader changes. This feature
turns that risk into a reviewable plan:

1. compare declared baseline and current revisions;
2. classify optional repository paths into the same dependency vocabulary;
3. evaluate each existing run manifest;
4. report the smallest affected evidence set;
5. fail when evidence is blocked or requires reauthorization.

The engine is deliberately conservative. A conservative classification may require a
rerun that turns out not to be necessary; a permissive classification can let stale
evidence approve a changed agent.

## Why the dependency graph matters

The dependency graph is the map between a change and the evidence it can invalidate.
It is not a model-quality score and it does not infer semantic truth from source
text. It is a bounded planning layer above the provider adapters and below a human
release decision.

The first release accepts safe revision identifiers and repository paths. It does
not parse raw traces, prompts, tool arguments, provider responses, or credentials.

## Run the synthetic example

```bash
uv run python tools/agent_impact_plan.py \
  --baseline-revisions examples/change-impact/baseline-revisions.json \
  --current-revisions examples/change-impact/current-revisions.json \
  --manifest examples/run-manifest/manifest.json \
  --changed-path policies/release-policy.json \
  --markdown \
  --fail-on-rerun
```

The command should return a non-zero status because the policy revision changed.
That is the intended control: the old result is not silently reused.

## GitHub Actions adoption

The CLI is suitable for an opt-in pull-request workflow. A caller supplies a
baseline revision file, a current revision file, and one or more metadata-only run
manifests. The workflow may pass Git paths from `git diff --name-only` and use
`--fail-on-rerun` after the team has reviewed the dependency mappings.

This repository keeps the first example local and synthetic. It does not add
provider credentials, live model calls, or automatic production approval.
