# Bounded synthetic rerun executor

## What this adds

The change-impact planner can identify stale evidence and name the checks that
should run next. The bounded rerun executor makes that next step executable for
the public synthetic harness:

1. read the existing change-impact plan inputs;
2. select the registered checks for affected evidence;
3. refuse unknown check IDs before dispatch;
4. run one offline synthetic suite through a code-side allowlist;
5. require both the guarded positive path and its known negative control; and
6. emit only identifiers, counts, statuses, digests, reason codes, and limits.

The registry remains metadata. It contains labels, not shell commands or import
paths. Adding a new executable check requires a reviewed code change as well as a
registry update.

## Run the example

From the repository root:

```bash
uv run python tools/rerun_executor.py \
  --baseline-revisions examples/change-impact/baseline-revisions.json \
  --current-revisions examples/change-impact/current-revisions.json \
  --manifest examples/run-manifest/manifest.json \
  --registry examples/change-impact/evidence-registry.json \
  --changed-path policies/release-policy.json \
  --markdown \
  --fail-on-noncompleted
```

The example changes the policy dependency. The planner therefore selects the
three checks in the example registry, and the executor should return
`rerun_completed` after catching all three negative controls.

Use `--output path/to/result.json` to save the machine-readable result. The
output intentionally does not contain reports, prompts, traces, tool payloads,
credentials, or provider responses.

## Current allowlisted checks

- `authorization-negative-controls`: the unsafe synthetic authorization path
  fails while the guarded authorization path completes;
- `tool-safety-regression`: replacing the required policy tool is caught;
- `evidence-completeness-gate`: removing shipping verification is caught;
- `abstention-negative-controls`: removing a required abstention is caught; and
- `evaluator-validity-negative-controls`: the independent evaluator catches
  the harness's planted false passes.

The check names are stable identifiers. They are not a promise that the same
checks are sufficient for a different system or decision target.

## Statuses and limits

- `not_required`: the plan found no affected evidence;
- `rerun_completed`: every selected check completed and caught its required
  negative control;
- `blocked`: the plan or a selected check cannot support reuse; and
- `refused`: an input or check ID was outside the executor contract.

The default local limits are eight checks and thirty seconds. This phase is
offline, so it makes no model requests and has no provider spend. The elapsed
time limit is still enforced: a result that exceeds it is blocked rather than
accepted as a successful rerun.

## What it does not do

The executor does not call OpenAI, Anthropic, or another provider; read
credentials; make network requests; execute registry-supplied commands; write
production systems; or approve release. A completed rerun is evidence that the
declared synthetic controls ran. A human or separately reviewed release workflow
must make the reauthorization decision.
