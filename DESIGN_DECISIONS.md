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
