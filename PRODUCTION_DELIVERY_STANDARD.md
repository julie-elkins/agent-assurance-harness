# Production Delivery Standard

This is a reusable standard for deciding whether a software change can reach
production without being checked, noticed, or reversible.

It answers a different question from a test suite:

> Could a second person ship this change, detect a failed release, and unship
> it using only the repository, the delivery system, and committed
> documentation?

This standard is technology-neutral. It applies to services, libraries,
agents, MCP servers, data tools, and scheduled jobs. It does not replace
security review, code review, testing, monitoring, or incident response.

## When to apply it

Apply the standard at project intake, before implementation becomes expensive.
For each point, record one of:

- **Satisfied** — the repository or delivery system contains the required
  evidence.
- **Breached** — the control is absent or weaker than required.
- **Not checkable** — the available evidence cannot establish the answer.

“Not checkable” is not a pass. An absent signal is not evidence that the
control exists.

## The ten controls

### 1. The build runs in CI, and CI is the gate

The package must be built by an automated continuous-integration (CI) workflow,
and that workflow must block merge or release when the build fails.

Why: a package built only on a workstation has no reliable record of which
source state produced the deployed artifact.

Evidence: a versioned workflow, a required status check, and a release step
that consumes the checked artifact.

### 2. The protected branch requires the gate

The branch that produces releases must require the relevant CI status checks and
review rules.

Why: a green workflow that can be bypassed is advisory, not a delivery control.

Evidence: repository branch-protection settings or an equivalent enforced
policy. A repository document alone is not enough.

### 3. Tests run in the gate, not only in a runbook

Unit, integration, privacy, and negative-control tests must run automatically
on the path that can merge or release the change.

Why: “the tests pass” must describe the change being shipped, not a command
someone may remember to run later.

The gate must also make skipped tests visible. A test suite that reports
success while silently skipping the important check is not a passing gate.

### 4. Drift checks block when drift is unsafe

Dependency, schema, provider-contract, baseline, and configuration drift checks
must block when the change violates the declared contract.

Why: a warning on a manual delivery path reports to whoever happens to run it;
that person may be nobody.

If drift is intentionally allowed, record the owner, expiry, and replacement
plan as metadata.

### 5. Consequential configuration has a repository source of truth

Lists, policies, environment contracts, release settings, and other inputs
that change what the system does must resolve from versioned project or
platform configuration—not from one person's home directory.

Why: a home-directory source of truth is single-copy, difficult to review, and
unavailable to the next operator or a clean build environment.

### 6. A second person can ship from a fresh checkout

A second operator must be able to build, test, release, and recover the system
from committed documentation and accessible delivery configuration.

Why: if shipping requires a conversation with one person, the practical
bus factor (the number of people who can perform the operation) is one.

Test this by following the instructions from a clean checkout, not by checking
whether the author can still use a familiar workstation.

### 7. Alerts reach a team destination

Operational alerts must route to a maintained team destination, with an owner
for the alert definition and a documented response path.

Why: an alert sent only to one person can be functionally disabled by leave,
role change, or mailbox failure.

The destination, escalation path, and alert-health check must be reviewable
without exposing credentials or customer data.

### 8. Rollback is named and has been executed once

For each releasable artifact, name the rollback mechanism, its target, its
verification, and its limits. Execute a safe rehearsal before relying on it.

Why: an untested rollback is a plan. A rehearsal is evidence that the stated
recovery path works for the state it actually controls.

Name what rollback cannot undo. A code revert does not automatically reverse an
external message, database deletion, ticket update, or other side effect.

### 9. Deprecated spikes are visibly deprecated

An experiment, prototype, or predecessor must be marked deprecated or removed
when it stops being the active plan.

Why: an orphan that still builds or resolves can be mistaken for a supported
component by the next operator, reviewer, or agent.

Record the replacement, owner, and removal condition. Do not leave an old
component looking production-ready by accident.

### 10. Manual publishing has an owner and procedure

If publishing is manual, document who may publish, how the version changes,
which artifact is approved, how the release is verified, and what consumers
must update.

Why: undocumented publishing creates version drift and leaves the repair work
to whoever notices it.

Prefer an automated, reviewable publishing path when the platform supports it.

## Minimum intake record

For each project, retain this small record with the build or review:

| Control | Status | Evidence | Owner | Cost if wrong |
| --- | --- | --- | --- | --- |
| CI build is the gate |  |  |  |  |
| Protected release branch |  |  |  |  |
| Tests run automatically |  |  |  |  |
| Unsafe drift blocks |  |  |  |  |
| Configuration source of truth |  |  |  |  |
| Second-person ship path |  |  |  |  |
| Team alert destination |  |  |  |  |
| Rollback rehearsed |  |  |  |  |
| Spikes deprecated |  |  |  |  |
| Publishing procedure |  |  |  |  |

The “cost if wrong” column matters because a missing control is not just a
checklist gap. It identifies what can reach production unnoticed, what becomes
single-person knowledge, or what cannot be undone.

## What this standard does not prove

A clean delivery-path result does not prove that the code is correct, secure,
private, performant, or suitable for a live model. Those require their own
technical, security, data, and operational evidence.

It proves only that the route from change to production has been made
observable, enforceable, operable by more than one person, and bounded by an
explicit recovery decision.
