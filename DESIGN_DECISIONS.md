# Design decisions

This file explains the choices that shape the Agent Assurance Harness. It is a
learning aid and reviewer map, not a claim that one architecture is universally
correct. The implementation and tests remain the source of truth.

## Keep the required path synthetic and provider-neutral

**Decision:** Run the required CI path against deterministic synthetic scenarios and
provider-neutral adapter contracts.

**Instead of:** Making CI depend on live model calls, provider credentials, or changing
hosted services.

**Why:** A pull request needs a repeatable answer about whether the declared evidence
contract still holds. Synthetic fixtures make that answer safe to run on every change
and keep private inputs outside the public repository.

**Official guidance considered:** OpenAI evaluation guidance, Anthropic provider
documentation, and the AWS Agentic AI Lens were used as context for separating
evaluation, provider behavior, security, and operational boundaries. The repository
implements only the declared synthetic contract.

**Verification:** The CI workflow runs the synthetic suite, adapter conformance,
negative controls, boundary checks, and release checks.

**Costs if wrong:** Live-provider behavior and provider-specific regressions remain
outside the required path and need a separately bounded local adapter.

**What this does not prove:** A passing synthetic run does not prove general model
quality, production authorization, deployment health, or hosted-service availability.

## Keep reports metadata-only

**Decision:** Reports carry identifiers, states, counts, hashes, reason codes, and
bounded usage observations rather than prompts, memory text, raw tool payloads, or
provider output.

**Instead of:** Exporting complete traces so a reviewer can inspect every input and
response in one public artifact.

**Why:** The public repository must demonstrate the control without becoming a second
copy of protected or copyrighted material. The evaluator should prove the boundary,
not weaken it to make the report easier to read.

**Verification:** Boundary tests reject content-bearing fields, and the showcase,
portfolio, and memory-policy reports assert metadata-only output.

**Costs if wrong:** A reviewer may need a separate local-only debugging path to inspect
details that the public report intentionally omits.

**What this does not prove:** Metadata can show that a declared check ran and what state
it returned; it cannot establish semantic truth of hidden content.

## Require a deliberately unsafe negative control

**Decision:** Every important positive path includes a known-bad case that the evaluator
must catch.

**Instead of:** Treating a green positive example as sufficient evidence that the gate
works.

**Why:** A negative control—an intentionally degraded case—tests the evaluator's ability
to block the failure it claims to protect against. This is especially important for
memory trimming, where lower cost can hide lost evidence.

**Verification:** The suite runs unsafe adapters and mutations, and CI fails if the
expected degradation is not caught.

**Costs if wrong:** Negative fixtures require maintenance when the evidence contract
changes, but removing them makes evaluator regressions easier to miss.

**What this does not prove:** Catching known failures does not prove that the evaluator
will find every future failure.

## Separate memory-policy safety from provider cache mechanics

**Decision:** Test agent-managed memory selection in this harness while keeping
provider-managed prompt-cache helpers in `elkins-llm-promptcache`.

**Instead of:** Coupling one repository to a provider SDK or claiming that prefix-cache
usage proves an agent chose safe context to retain.

**Why:** A provider cache reuses a request prefix; a memory policy decides which prior
context should remain available. They affect one another but have different contracts.
Keeping them separate lets the safety evaluator run offline and lets provider adapters
report real usage only through an explicit local boundary.

**Verification:** The bounded memory-policy lane checks required evidence, workflow
isolation, refusal, relative cost, and relative latency independently from provider
cache usage.

**Costs if wrong:** The projects need an adapter contract before a live integration can
be evaluated end to end.

**What this does not prove:** The synthetic lane does not establish live provider cache
savings or production performance.

## Teaching path

Start with the [Agent Systems Design Guide](https://github.com/julie-elkins/agent-systems-design-guide),
then run the [showcase](SHOWCASE.md), read the relevant implementation, and inspect the
negative control. The sequence is intentional: understand the risk, see the contract,
run the control, and then examine the code.

## Require a change-impact plan before reusing evaluation evidence

**Decision:** Compare baseline and current dependency revisions, classify optional
repository paths, and produce a bounded rerun plan before allowing old evidence to
support a changed agent decision.

**Instead of:** Rerunning every evaluation for every change, or treating unchanged
metadata as proof that all old evidence is still valid.

**Why:** Model, prompt, tool, policy, data, harness, environment, and grader changes
do not affect every evaluation equally. A dependency graph makes the affected scope
visible and gives engineers the smallest reviewable next action. The engine remains
provider-neutral because it consumes the existing run-manifest contract rather than
parsing provider content.

**Verification:** `tools/agent_impact_plan.py` compares synthetic revision maps,
classifies safe Git paths, evaluates existing manifests, emits JSON or Markdown, and
returns a non-zero status with `--fail-on-rerun` when evidence is stale or blocked.
The unit tests cover unchanged, changed, blocked, and path-driven cases.

**Costs if wrong:** Conservative mappings can request an unnecessary rerun and path
classification cannot understand every project convention. That cost is deliberately
accepted because a false rerun is reviewable, while a false clean result can silently
reuse invalid evidence.

**What this does not prove:** The plan does not prove model quality, semantic truth,
production safety, or that every affected test has been listed. It is a change-impact
gate and rerun planner, not an automatic release approval.

## Use a named evidence registry instead of executable rerun commands

**Decision:** Extend the change-impact plan with a registry that declares each
evidence scope, its dependency categories, named rerun check IDs, and an owner.

**Instead of:** Storing shell commands in public metadata and executing whatever a
registry author supplies.

**Why:** Engineers need an actionable answer after a change, but a public registry
must not become an unreviewed command-execution surface. Check IDs keep the plan
portable and let a trusted local or CI workflow map them to approved commands.

**Verification:** Strict registry loading rejects unsupported fields, duplicate
entries, unknown dependencies, whitespace-bearing identifiers, and check values that
do not match the lowercase identifier format. An affected evidence item without a
registry entry becomes `blocked`.

**Costs if wrong:** The first release stops at a named rerun plan, so teams must
connect check IDs to their own trusted workflow. That is slower than executing
commands immediately but preserves reviewability and avoids arbitrary execution.

**What this does not prove:** A registered check ID does not prove that the check ran
or passed. The trusted workflow must record the resulting evidence and reauthorization
separately.

## Bind provider-shaped runs through metadata-only receipts

**Decision:** Normalize accepted and refused OpenAI- and Anthropic-shaped adapter
results into one provider evidence receipt and require the evidence ID to resolve to
the registry.

**Instead of:** Publishing provider response formats, exporting translated traces, or
letting an unowned provider run become reusable evidence.

**Why:** Provider-specific adapters are useful at the boundary, but engineers need a
portable record that says which provider-shaped run produced the evidence, what
decision it belongs to, and which trusted checks apply after change. The receipt
connects those facts without copying provider content into the public repository.

**Verification:** The synthetic CLI runs both mocked providers, produces one shared
receipt shape, validates the output schema, refuses unknown evidence IDs, and turns
over-budget provider results into bounded refusal receipts. Serialized receipts are
checked for raw provider text and tool-result identifiers.

**Costs if wrong:** The public receipt cannot support detailed provider debugging.
That debugging remains inside the local adapter boundary, which keeps the portable
artifact safe but makes diagnosis a two-artifact workflow.

**What this does not prove:** An accepted receipt proves that the adapter returned a
contract-valid synthetic run and that the registry binding was present. It does not
prove live provider quality, semantic truth, a signed attestation, or that the
registered rerun checks passed.

## Validate receipts before change-impact decisions

**Decision:** Require the change-impact planner to validate an optional provider
receipt's evidence ID, registry-entry digest, baseline revision digest, acceptance
status, and harness revision before using it in an impact decision.

**Instead of:** Treating a receipt as trustworthy because it names a familiar
provider, model, or scenario.

**Why:** A receipt is useful only if it is bound to the evidence scope and revision
that the planner is evaluating. Digest checks make stale or misowned receipts block
explicitly without exposing provider content.

**Verification:** The end-to-end synthetic path generates OpenAI and Anthropic
receipts against baseline revisions, feeds them to the impact planner, and reports
accepted provider IDs plus `rerun_required` after a policy revision. Missing,
rejected, registry-mismatched, or revision-mismatched receipts return `blocked`.

**Costs if wrong:** A receipt generated after a change cannot be reused for the
baseline decision; it must be regenerated and reviewed. This adds an explicit step
but prevents a newer result from being misrepresented as evidence for an older state.

**What this does not prove:** Receipt validation does not prove that the registered
checks passed or that a provider's live output was high quality. It only proves the
metadata binding required before the next assurance decision.

## Make the public explorer show the complete receipt-to-rerun path

**Decision:** Extend the local Evidence Validity Explorer with an optional provider
receipt lane that shows accepted OpenAI- and Anthropic-shaped receipts, the impact
planner's `rerun_required` decision after a revision change, named rerun checks and
owner, plus a deliberately stale receipt that is blocked.

**Instead of:** Publishing another provider dashboard or showing a provider response
transcript that would be difficult to compare, unsafe to publish, and disconnected
from the canonical change-impact decision.

**Why:** A reviewer should be able to see the whole control in one screenshot:
portable metadata is accepted, a dependency changes, the planner names the work, and
stale evidence cannot be reused. The explorer remains a presentation layer over the
same evaluator and impact planner, so the visual demo cannot silently invent a second
decision rule.

**Verification:** The integration test generates both mocked provider receipts, renders
the page with a policy revision, checks for `rerun_required`, named checks, and owner,
and verifies the revision-mismatch negative control is `blocked`. The rendered page
contains identifiers and statuses only.

**Costs if wrong:** The page becomes denser and may require a larger screenshot, while
the static demo still covers one synthetic evidence item rather than a fleet. That
tradeoff is accepted because the added context makes the core contribution legible
without introducing a hosted service or public provider data.

**What this does not prove:** The screenshot does not prove live OpenAI or Anthropic
quality, production safety, or that the named checks passed. It demonstrates the
portable metadata contract and the decision boundary around reuse.

## Measure the measurement system before trusting its safety case

**Decision:** Add a local-first Monitorability and Evaluator Validity Workbench to the
existing harness. It measures monitor recall, benign false-positive rate, evaluator
agreement, held-out performance, evaluation-awareness gaps, uncertainty intervals, and
run-manifest reauthorization before packaging a metadata-only safety case.

**Instead of:** Adding another replay engine, provider dashboard, or uncalibrated LLM
judge that produces a safety score without testing whether the measurement system can
detect known and held-out hazards.

**Why:** A safety claim is only as useful as the monitor and evaluator supporting it.
Separating the monitor's detection from the evaluator's agreement makes false passes,
benign over-blocking, held-out misses, and evaluation-aware behaviour visible. Reusing
the existing manifest and explorer keeps the new work connected to the evidence and
reauthorization controls already in this repository.

**Verification:** The synthetic fixture contains calibration, held-out, benign-control,
and paired evaluation-awareness cases. Tests verify metric separation, uncertainty
metadata, the held-out miss negative control, revision-triggered review, safety-case
human review, CLI refusal, and explorer rendering.

**Costs if wrong:** Thresholds and synthetic labels can create false confidence if a
reader treats them as production limits. The report therefore labels thresholds as
modelling assumptions, includes limitations, and always requires human review. The
workbench does not claim live-provider quality.

**What this does not prove:** Passing the workbench does not prove agent safety,
semantic truth, monitor generalisation beyond the declared scenario pack, or deployment
approval. Signed attestations and cryptographic producer identity remain future work.

## Make monitorability a blocking CI contract

**Decision:** Add `tools/monitorability_ci_gate.py` to the existing reliability
workflow. It runs the positive synthetic report, proves the held-out monitor-miss
negative control is detected, and proves that a changed revision requires review.

**Instead of:** Running only the positive example in CI or embedding expected-failure
shell commands directly in the workflow.

**Why:** A positive report alone can pass while the negative control stops working or
the reauthorization boundary is accidentally removed. The wrapper keeps all three
states in one deterministic contract and writes bounded artifacts even when the gate
blocks.

**Verification:** The integration tests cover a passing gate and a blocked gate when
the changed revision map is unchanged. The workflow runs after repository-boundary and
dependency checks and uploads the positive, negative, changed-revision, safety-case,
and summary JSON artifacts.

**Costs if wrong:** The reliability workflow becomes slightly longer and adds five
small artifacts per run. That cost is accepted because the artifacts make a failed
measurement-system control inspectable without exposing content-bearing evidence.

**What this does not prove:** A passing CI gate does not prove live-provider safety,
deployment readiness, or that the monitor generalises beyond the checked-in synthetic
scenario pack. Human review remains required.

## Add a synthetic shadow-execution boundary

**Decision:** Add a fixture-driven, metadata-only shadow-execution contract that
compares an agent's identifier-only intended effect with a synthetic observed
effect and returns `allow`, `block`, or `human_review`.

**Instead of:** Executing real commands in a sandbox, adding a hosted gateway,
or creating a second orchestration runtime before the action and evidence
contract is reviewable.

**Why:** The public harness can demonstrate the pre-effect decision boundary
without adding a filesystem, GitHub, AWS, messaging, browser, or provider write
surface. Checking authority before simulation and treating mismatches or
ambiguous state as human review also addresses the crash-after-effect failure:
an action can change state before its recorder proves what happened.

**Verification:** The synthetic fixture covers a matched effect, missing
authority, observed mismatch, approval-required action, and ambiguous state.
Tests verify that missing authority blocks before simulation, matched effects
are allowed without real writes, and every receipt states what it does not
prove.

**Costs if wrong:** The first version does not prove operating-system
isolation, rollback, live-tool compatibility, or production safety. A future
adapter will need a separate security and delivery-path review before it can
connect a real tool.

**What this does not prove:** A passing shadow report proves only that the
declared synthetic controls returned their expected decisions. It does not
prove that a live tool is safe, reversible, or free of hidden side effects.
