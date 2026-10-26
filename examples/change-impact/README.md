# Agent change-impact demo

This synthetic example shows why old evidence cannot silently approve a changed
agent. The policy revision changes from `policy-r1` to `policy-r2`, so the existing
run manifest requires a rerun.

Run the JSON report:

```bash
uv run python tools/agent_impact_plan.py \
  --baseline-revisions examples/change-impact/baseline-revisions.json \
  --current-revisions examples/change-impact/current-revisions.json \
  --manifest examples/run-manifest/manifest.json \
  --registry examples/change-impact/evidence-registry.json \
  --changed-path policies/release-policy.json \
  --json
```

The command exits `0` when it only reports the plan. Add
`--fail-on-rerun` to make stale evidence fail a pull-request gate.

The registry contributes the named checks
`authorization-negative-controls`, `tool-safety-regression`, and
`evidence-completeness-gate`. These are identifiers for a trusted workflow; they
are not shell commands and are not executed by this tool.

The report contains identifiers, revisions, paths, states, and reason codes only.
It does not inspect prompts, tool payloads, model output, credentials, or private
traces.
