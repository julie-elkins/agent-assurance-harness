# Showcase the Agent Assurance Harness

This is the fastest way for an outside reviewer to see what the project does and why
the controls matter.

The showcase has six related lanes:

1. An offline synthetic lane for repeatable CI (continuous integration, the automated
   checks that run before a change can merge).
2. An opt-in public-course lane for demonstrating the same metadata-only review path
   against a real public course checkout.
3. A launch-to-field lane for demonstrating how a capability becomes a demo, lab, and
   quick-reference guide with freshness and feedback controls.
4. An instructor-calibration lane for demonstrating observer consistency and coaching
   recommendations.
5. A portfolio-assurance lane for joining the independent evidence paths into one
   reviewer handoff.
6. A developer-workflow lane for proving that a plausible green coding-agent result
   still needs the required verification evidence.

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
controls, one Course Doctor review packet, the launch-to-field enablement pack, and
the instructor-calibration rubric. A mutation control is a deliberately changed
synthetic result used to prove that the evaluator catches a known failure.

The output contains identifiers, statuses, counts, and hashes only. It does not contain
lesson text, prompts, credentials, provider output, or source paths.

Expected successful output:

```text
# Agent Assurance Harness Showcase

## Offline assurance

- Scenarios checked: `10`
- Guarded agent: `PASS`
- Evaluator controls caught: `2`
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

## Portfolio dashboard

The combined report can also be rendered as a local dashboard. A dashboard is a
reviewer-facing view of one run, not a hosted monitoring service and not a second
evaluator:

```bash
uv run python tools/portfolio_assurance_report.py \
  --workspace /tmp/agent-reliability-portfolio \
  --output /tmp/agent-reliability-portfolio.json \
  --fail-on-findings
uv run python tools/portfolio_dashboard.py \
  --input /tmp/agent-reliability-portfolio.json \
  --output /tmp/agent-reliability-portfolio.html
```

The HTML view shows the portfolio decision, lane states, caught and missed controls,
human gates, the missing-lane negative control, and the limits of the result. It contains
metadata only: no prompts, traces, source text, credentials, provider output, or local
source paths. See [`docs/PORTFOLIO_DASHBOARD.md`](docs/PORTFOLIO_DASHBOARD.md) for the
input boundary and refusal behaviour.

## Evidence Validity Explorer

The Evidence Validity Explorer is the shortest visual demonstration of the
provider-neutral run-manifest idea. It places the same evidence record beside two
revision snapshots: the current state and a deliberately changed negative control
(a case that should be caught):

```bash
uv run python tools/evidence_validity_explorer.py \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --changed-revisions examples/run-manifest/changed-revisions.json \
  --provenance examples/run-manifest/evidence-provenance.json \
  --missing-provenance examples/run-manifest/evidence-provenance-missing.json \
  --output /tmp/agent-evidence-validity-explorer.html
```

Open the generated file locally. The current snapshot remains `reauthorized`; the
changed prompt and tool revisions become `reauthorization_required`, and the missing
producer record becomes `evidence_missing`, blocking reuse. The page also shows the
bounded receipt, grader-validity, and synthetic deployment metadata. It is suitable for
a public screenshot without exposing provider output, credentials, personal cloud
details, or private work.

See [`docs/EVIDENCE_VALIDITY_EXPLORER.md`](docs/EVIDENCE_VALIDITY_EXPLORER.md) for
the input boundary and deliberate limits.

## Evidence provenance negative control

The provenance gate adds a second, narrower question: did a producer actually record
an evidence artifact for the exact run manifest? Provenance means metadata about where
the result came from. The gate checks only digests, identifiers, counts, and status; it
does not read or publish traces, transcripts, prompts, tool payloads, or provider output.

Run the positive synthetic fixture:

```bash
uv run python tools/evidence_provenance_gate.py \
  --manifest examples/run-manifest/manifest.json \
  --provenance examples/run-manifest/evidence-provenance.json \
  --markdown \
  --fail-on-missing
```

It returns `EVIDENCE_OBSERVED` with exit code `0`. Then run the deliberate negative
control:

```bash
uv run python tools/evidence_provenance_gate.py \
  --manifest examples/run-manifest/manifest.json \
  --provenance examples/run-manifest/evidence-provenance-missing.json \
  --markdown \
  --fail-on-missing
```

It returns `EVIDENCE_MISSING` with exit code `1`. That failure is intentional: a
successful-looking manifest cannot support reuse when no producer evidence was observed.
See [`docs/EVIDENCE_PROVENANCE.md`](docs/EVIDENCE_PROVENANCE.md) for the contract and
limits.

## Instructor calibration

- Ready for human sign-off: `PASS`
- Degraded controls caught: `4`
- Rubric covers: `technical_accuracy`, `hands_on_execution`, `live_debugging`,
  `audience_adaptation`, and `safety_boundary`

The result recommends coaching or human sign-off; it does not certify an instructor
automatically.

This demo is synthetic, offline, and metadata-only.
```

## Developer workflow assurance

The developer workflow lane is the most direct portfolio path for an engineering hiring
manager. It asks whether a coding-agent change has the evidence needed to be reviewed,
not merely whether one test command returned green:

```bash
uv run python tools/developer_workflow_report.py \
  --output /tmp/agent-reliability-developer-workflow.json \
  --markdown \
  --fail-on-findings
```

Expected summary:

```text
# Developer workflow assurance

- Decision: `PASS`
- Synthetic packs checked: `6`
- Guarded reference: `PASS`
- Green-but-unaudited negative control caught: `YES`
```

The negative control is intentionally incomplete: it reports a passing test result but
omits required security and dependency evidence. The report must block it. This shows
why evidence completeness matters in developer tooling: a green check can be true and
still be insufficient for a merge decision.

The lane also covers ambiguous scope, untrusted build-log output, and protected release
actions. It is synthetic and offline; it does not claim to prove source-code correctness
or general live-agent reliability. See
[`docs/DEVELOPER_WORKFLOW_ASSURANCE.md`](docs/DEVELOPER_WORKFLOW_ASSURANCE.md).

## Agent workflow teaching lab

The learner-facing path is a separate, short command so a teaching walkthrough does
not make the required assurance showcase depend on presentation text:

```bash
uv run python examples/agent-workflow-teaching-lab/run_lab.py
```

It demonstrates a synthetic request that returns transport success while its context
is empty. The naive path retries and reports success; the guarded path records a
semantic outcome, stays within retry and estimated-cost ceilings, and escalates for
human approval. The lab is offline and metadata-only. It does not prove live model
quality, production observability, learner reach, or adoption.

## Combined portfolio assurance report

For a reviewer who wants the full public story in one command:

```bash
uv run python tools/portfolio_assurance_report.py \
  --workspace /tmp/agent-reliability-portfolio \
  --output /tmp/agent-reliability-portfolio.json \
  --markdown \
  --fail-on-findings
```

Expected summary:

```text
# Portfolio Assurance Report

Decision: `ready_for_human_review`

| Lane | Status | Degraded controls | Human gate |
| --- | --- | ---: | --- |
| `agent_assurance` | `passed` | `4` | CI and human merge approval remain required. |
| `course_doctor` | `passed` | `4` | Human adjudication remains required before content changes. |
| `launch_to_field` | `passed` | `4` | Human approval remains required before publication. |
| `instructor_calibration` | `passed` | `4` | Qualified observer sign-off remains required. |
| `delivery_path` | `passed` | `0` | Release approval, deployment controls, and monitoring remain external. |

Blocking lanes: none
Missing lanes: none

Orchestration controls caught: `portfolio-ready`, `portfolio-missing-instructor-lane`

Orchestration controls missed: none

The report joins inspectable evidence; it does not replace human review, release
approval, or instructor certification.
```

The missing-instructor-lane control is deliberately blocked internally to prove that the
join cannot call an incomplete portfolio ready. The final report contains only lane
identifiers, states, counts, and human-gate descriptions.

## Add the public Claude course locally

The optional public-course lane reads a separately checked-out revision of
[Claude Architect Lab](https://github.com/julie-elkins/claude-architect-lab):

```bash
uv run python tools/portfolio_assurance_report.py \
  --course-root /path/to/claude-architect-lab \
  --course-id claude-architect-lab \
  --workspace /tmp/agent-assurance-public-course-portfolio \
  --output /tmp/agent-assurance-public-course-portfolio.json \
  --markdown \
  --max-rows 1000 \
  --max-requests 50
```

On the reviewed checkout, the lane records the course revision, 335 claim rows, 13
fetched pages, evidence-tier counts, and safe locations for the nine known findings.
The current decision is `review_required`, which means a human should inspect those
locations before changing course content. The report does not contain lesson text,
quotes, source bytes, or the local checkout path.

## Turn public-course findings into a review packet

After the portfolio run identifies findings, create the bounded human worklist:

```bash
uv run python tools/public_course_review_packet.py \
  --course-root /path/to/claude-architect-lab \
  --course-id claude-architect-lab \
  --output /tmp/claude-course-review-packet.json \
  --markdown \
  --max-rows 1000 \
  --max-requests 50
```

The packet maps each finding to a lesson, claim number, evidence tier, priority, and
recommended action. It starts every item as `open`; human review is still required.

## Record the review decision

The packet is a worklist, not a decision. Copy the packet digest and safe finding IDs
into a local decisions file based on
`examples/public-course-demo/review-decisions.template.json`, then run:

```bash
uv run python tools/public_course_review_adjudication.py \
  --packet /tmp/claude-course-review-packet.json \
  --decisions /tmp/claude-course-review-decisions.json \
  --output /tmp/claude-course-review-adjudication.json \
  --markdown \
  --fail-on-open
```

The result records dispositions without exporting course text or reviewer rationale.
`adjudicated` means every known finding has a disposition; the underlying course
evidence decision and human approval boundary remain visible.

## Create the change plan

After adjudication, generate the final metadata-only handoff before a future human edit:

```bash
uv run python tools/public_course_change_plan.py \
  --packet /tmp/claude-course-review-packet.json \
  --adjudication /tmp/claude-course-review-adjudication.json \
  --output /tmp/claude-course-change-plan.json \
  --markdown \
  --fail-on-block
```

The plan shows the safe lesson and claim locations, proposed action, disposition, and
required re-check. It contains no replacement wording or source text. A ready plan still
requires human approval, and a fresh course-verifier run after the edit.

## Verify after a human change

Compare the plan with the later verifier report after the human edit:

```bash
uv run python tools/public_course_post_change.py \
  --change-plan /tmp/claude-course-change-plan.json \
  --post-report /tmp/claude-course-adapter-after.json \
  --output /tmp/claude-course-post-change.json \
  --markdown \
  --fail-on-block
```

The result is `verified_targeted_scope` only when the revision changed, every planned
target recovered, and no new blocking finding appeared outside the planned scope. This is
not a full-course correctness claim. Accepted-risk targets are rechecked and fail if they
become blocking; human approval is still required before publication.

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
