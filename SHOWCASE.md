# Showcase the Agent Assurance Harness

This is the fastest way for an outside reviewer to see what the project does and why
the controls matter.

The showcase has two lanes:

1. An offline synthetic lane for repeatable CI (continuous integration, the automated
   checks that run before a change can merge).
2. An opt-in public-course lane for demonstrating the same metadata-only review path
   against a real public course checkout.
3. A launch-to-field lane for demonstrating how a capability becomes a demo, lab, and
   quick-reference guide with freshness and feedback controls.

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
controls, one Course Doctor review packet, and the launch-to-field enablement pack. A
mutation control is a deliberately changed synthetic result used to prove that the
evaluator catches a known failure.

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

## Example blocked finding (synthetic)

- Course: `course-pipeline-stale-source`
- What needs attention: Source is older than the allowed freshness window.
- Claim: `claim-pipeline-supported`
- Section: `section-synthetic-guidance`
- Evidence: `source-approved-docs`
- Source: `source-approved-docs`
- Freshness: `7200` seconds observed; `3600` seconds allowed

This deliberately blocked example shows where a review starts without exposing lesson
text or a source path. The full JSON report retains the complete machine-readable
metadata; the Markdown output uses plain-language labels and shortened detail.

## Launch-to-field enablement

- Ready pack: `PASS`
- Degraded controls caught: `4`
- Pack includes: `demo`, `lab`, `quick_reference`, and synthetic feedback signals

The ready pack still requires human approval before publication. Its degraded controls
demonstrate stale, wrong-source, unsupported-claim, and incomplete-pack behavior.

This demo is synthetic, offline, and metadata-only.
```

The exact counts are part of the current synthetic fixture contract. A changed count
should prompt a deliberate fixture or scenario review, not a README-only update.

## Public Claude course demonstration

The public-course lane reads a pinned local checkout of
[Claude Architect Lab](https://github.com/julie-elkins/claude-architect-lab). The course
remains its own source of truth; this repository does not copy or vendor its lessons.

Clone the course beside the harness, confirm the checkout revision, then run:

```bash
git -C /path/to/claude-architect-lab rev-parse HEAD
uv run python tools/claude_course_adapter.py \
  --course-root /path/to/claude-architect-lab \
  --course-id claude-architect-lab \
  --max-rows 1000 \
  --max-requests 50 \
  --output /tmp/claude-course-adapter-full.json \
  --markdown
```

The reviewed public course revision is
`f34d21087db73dd4f6b5bbd2b8a55601ace1d6fe`. If the checkout is at another revision,
the command remains useful, but it is no longer a reproducible run of the reviewed
course state. The command intentionally omits `--fail-on-findings`: the expected result
is a review worklist, not a clean pass.

This command reads the course's checked-in verifier and reports every claim row under
bounded limits. It keeps guide references, verbatim checks, identifier checks, and
uncovered claims separate. A missing quote or identifier becomes a review location, not
an automatic stale-content verdict. The report contains lesson and claim-row
identifiers, source URLs, read dates, states, and counts, but not course text or source
paths.

The full-course adapter is a local demonstration because its documentation sources can
change. The required showcase and CI gate remain synthetic and offline. A private,
rough draft without structured claim/source metadata is not a suitable public fixture;
the adapter will not invent dates, freshness windows, or locations.

Expected result for the pinned checkout:

```text
# Claude Course Verification

Decision: `REVIEW_REQUIRED`

- Course: `claude-architect-lab`
- Revision: `f34d21087db73dd4f6b5bbd2b8a55601ace1d6fe`
- Pages fetched: `13`
- Offline: `False`
- Counts: `{"counts_reconcile": true, "guide_reference_only": 205, "identifier_missing": 1, "identifier_present_only": 50, "offline": false, "rows_total": 335, "unable_to_check": 0, "uncovered": 44, "verbatim_not_found": 6, "verbatim_verified": 29}`

A `review_required` result means at least one row was not proven by the strongest
available check. It is not a claim that every unverified row is wrong.

## Findings with a concrete review signal

- `course/domain-1-agentic-architecture/lesson-1-3-subagent-invocation.md` —
  exact documentation wording was not found; human review is required.
  Claim row: `9`; evidence tier: `VERBATIM`;
  source: `https://code.claude.com/docs/en/sub-agents`
- `course/domain-1-agentic-architecture/lesson-1-7-session-state.md` —
  exact documentation wording was not found; human review is required.
  Claim row: `10`; evidence tier: `VERBATIM`;
  source: `https://code.claude.com/docs/en/sessions`
- `course/domain-1-agentic-architecture/lesson-1-7-session-state.md` —
  exact documentation wording was not found; human review is required.
  Claim row: `16`; evidence tier: `VERBATIM`;
  source: `https://code.claude.com/docs/en/sessions`
- `course/domain-2-tools-and-mcp/lesson-2-4-mcp-integration.md` —
  a documented identifier was not found; check for rename or removal.
  Claim row: `8`; evidence tier: `IDENTIFIER`;
  source: `https://code.claude.com/docs/en/mcp`
- `course/domain-4-prompting-and-output/lesson-4-3-structured-output.md` —
  exact documentation wording was not found; human review is required.
  Claim row: `10`; evidence tier: `VERBATIM`;
  source: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs`
- `course/domain-4-prompting-and-output/lesson-4-3-structured-output.md` —
  exact documentation wording was not found; human review is required.
  Claim row: `12`; evidence tier: `VERBATIM`;
  source: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs`
- `course/domain-4-prompting-and-output/lesson-4-3-structured-output.md` —
  exact documentation wording was not found; human review is required.
  Claim row: `16`; evidence tier: `VERBATIM`;
  source: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs`

## Evidence that remains incomplete

- `guide_reference_only` rows are not independent claim verification.
- `identifier_present_only` rows do not prove the claim's meaning.
- `uncovered` rows have no automated evidence tier.

This report contains identifiers, dates, URLs, states, and counts only; it does not
contain claim or source text.
```

The exact counts are a demonstration snapshot, not a permanent CI expectation. A
documentation change can legitimately change the result; the important behavior is
that the adapter preserves the evidence tiers and routes unresolved rows to review.

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
