# Developer Workflow Assurance

This lane demonstrates a practical question for coding agents:

> Is a change ready to merge, or did it merely produce a plausible green result?

It uses six synthetic developer-workflow packs:

- regression verification;
- dependency-lock verification;
- ambiguous-scope abstention;
- protected release authorization and reconciliation;
- untrusted build-log handling; and
- a negative control where tests are green but required security and dependency evidence
  is missing.

The lane runs two adapters through the same JSONL (JSON Lines, one JSON object per line)
boundary used by external integrations:

1. The guarded reference adapter supplies every required evidence identifier.
2. The degraded adapter intentionally omits security evidence for the
   `developer-green-but-unaudited` pack.

The result passes only when the guarded adapter passes and the negative control is
blocked. That pairing matters because a test suite that only demonstrates the happy path
can pass while the evaluator quietly misses the failure it was supposed to catch.

## Run it

From the repository root:

```bash
uv run python tools/developer_workflow_report.py \
  --output /tmp/agent-reliability-developer-workflow.json \
  --markdown \
  --fail-on-findings
```

The report is metadata-only. It contains pack identifiers, dimensions, counts, hashes, and
the overall decision. It does not contain prompts, source code, raw tool arguments,
provider output, credentials, or local repository contents.

## What the result proves

- Required workflow evidence can be declared as a versioned contract.
- A provider-neutral adapter can emit identifier-only evidence across a process boundary.
- A passing test result is not sufficient when the contract also requires security or
  dependency verification.
- Ambiguous scope and untrusted tool output can require abstention (a deliberate refusal
  to claim completion).
- Protected actions can require authorization, stable operation identity, idempotency
  evidence, and postcondition reconciliation (a readback that confirms the resulting
  state).

## What it does not prove

This is an assurance workflow demonstration, not a source-code correctness benchmark.
The packs use synthetic task identifiers and synthetic tool results. The lane does not
run a model, edit a checkout, execute a real test suite, or establish general live-agent
reliability.

The next credible extension would be a safe local task fixture with a real patch
comparison and test execution. That should be added only if it can preserve the
metadata-only public boundary and keep private source content out of the repository.
