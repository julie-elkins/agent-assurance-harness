# Showcase the Agent Assurance Harness

This is the fastest way for an outside reviewer to see what the project does and why
the controls matter.

The showcase has two lanes:

1. An offline synthetic lane for repeatable CI (continuous integration, the automated
   checks that run before a change can merge).
2. An opt-in public-course lane for demonstrating the same metadata-only review path
   against a real public course checkout.

The first lane is the required proof. The second lane is the practical demonstration.
Keeping them separate prevents a changing course repository or a network outage from
turning the required gate into an external-state test.

## One-command offline showcase

From the repository root:

```bash
uv sync --extra dev
uv run python tools/showcase_demo.py --markdown
```

The command runs the guarded synthetic agent, evaluator false-pass controls, mutation
controls, and one Course Doctor review packet. A mutation control is a deliberately
changed synthetic result used to prove that the evaluator catches a known failure.

The output contains identifiers, statuses, counts, and hashes only. It does not contain
lesson text, prompts, credentials, provider output, or source paths.

Expected successful output:

```text
# Agent Assurance Harness Showcase

## Offline assurance

- Scenarios checked: `9`
- Guarded agent: `PASS`
- Evaluator controls caught: `1`
- Mutation controls caught: `3`

## Course Doctor

- Review packets passed: `PASS`
- Packet counts: `{"completed": 1, "counts_reconcile": true, "failed": 0, "not_reviewed": 0, "packets_emitted": 1, "requested": 1, "timed_out": 0, "truncated": false}`

This demo is synthetic, offline, and metadata-only.
```

The exact counts are part of the current synthetic fixture contract. A changed count
should prompt a deliberate fixture or scenario review, not a README-only update.

## Public Claude course demonstration

The public-course lane reads a pinned local checkout of
[Claude Architect Lab](https://github.com/julie-elkins/claude-architect-lab). The course
remains its own source of truth; this repository does not copy or vendor its lessons.

Clone the course beside the harness, then run:

```bash
git -C /path/to/claude-architect-lab rev-parse HEAD
uv run python tools/course_doctor_report.py \
  --manifest examples/public-course-demo/manifest.json \
  --source-root /path/to/claude-architect-lab \
  --workspace /tmp/agent-assurance-public-course \
  --output /tmp/agent-assurance-public-course.json \
  --markdown
```

The manifest pins the public course revision to
`f34d21087db73dd4f6b5bbd2b8a55601ace1d6fe`. If the checkout is at another revision,
the command is still a useful local demonstration, but it is no longer a reproducible
run of the reviewed course state.

The example manifest selects one public lesson and supplies only metadata about the
claim-to-source relationship. The local adapter reads the bounded lesson bytes in
memory, fingerprints them, and discards them before producing the review packet.

This lane demonstrates the use case rather than proving the course is semantically
correct. The course repository's own citation, verification, accessibility, and
production checks remain responsible for course-specific quality.

## What to show in a screen recording

A three-to-five-minute recording can show:

1. The harness README and this showcase guide.
2. The offline command completing with the guarded path and controls caught.
3. The public course manifest and the local-course command.
4. The metadata-only review packet.
5. The live-provider command refusing before network access when `--allow-network` is
   omitted.
6. The guide's limitations: no automatic publishing, no provider credentials in CI,
   and no claim of general live-model reliability.

On macOS, `Shift–Command–5` opens the built-in screen-recording controls. Record the
terminal and repository files, never credential stores or environment-variable values.

## Bounded local live-provider demonstration

The live boundary is a connector that can call one approved provider endpoint while
keeping the evaluator and evidence contract unchanged. It is disabled by default and
is not part of CI.

Before a local run, set the credential in the process environment. Pass the credential
value through the shell or a secret manager; never put it in a command transcript,
manifest, source file, or report.

Example shape:

```bash
export OPENAI_API_KEY='set-this-in-your-local-shell-only'
uv run agent-reliability \
  --live-provider openai \
  --scenario-id unauthorized-side-effect \
  --model YOUR_MODEL_ID \
  --allow-network \
  --max-requests 1 \
  --max-output-tokens 64 \
  --max-elapsed-seconds 5 \
  --max-estimated-cost-usd 0.01 \
  --estimated-cost-usd-per-request 0.001 \
  --json
```

The live boundary requires explicit network opt-in, one request, fixed official
endpoints, a timeout, an output-token ceiling, and a conservative estimated spend
ceiling. It makes no retry, rejects redirects, rejects malformed structured output,
and emits no provider text.

The live path is a local integration demonstration, not evidence that a model is
generally reliable, that the provider interpreted the request correctly, or that the
system is ready for unattended production deployment.

## Reviewer takeaway

The project demonstrates a complete assurance boundary:

```text
agent or course input
        ↓
bounded adapter
        ↓
identifier-only evidence
        ↓
evaluator and negative controls
        ↓
metadata-only review packet
        ↓
human approval before any future change
```

The important behavior is not that every input passes. It is that missing, stale,
wrong-source, malformed, or unauthorized evidence becomes visible and blocks the next
consequential step.
