---
name: agent-assurance-harness
description: Extend or review this provider-neutral Agent Assurance Harness when a change affects evidence, abstention, safety controls, reusable consumers, or CI delivery gates.
---

# Agent Assurance Harness

Use this skill when changing the public `agent-reliability-lab` repository or adapting its
assurance contract for a synthetic consumer.

## Outcome

Leave a deterministic, metadata-only control that proves the requested reliability
property before merge. A positive path is not enough: include a deliberately degraded
negative control and make the delivery gate fail when it is not caught.

## Required boundaries

- Use public synthetic data only. Never add credentials, unpublished exam content,
  prompts, raw traces, provider payloads, or private URLs.
- Keep provider integrations mocked or injected. Do not add live network calls to CI.
- Real public documentation may be refreshed only through the fixed official-source
  boundary; follow redirects only to an allow-listed official host, enforce timeout and
  response-size limits, hash the response, and discard its body. CI must use synthetic
  fixtures for deterministic controls.
- Reports may contain identifiers, states, counts, hashes, and stable failure reasons;
  they must not contain raw evidence, commands, payloads, or secrets.
- If a reusable GitHub Action changes, pin consumer examples to an immutable commit.
  Compatibility requires both the declared versions and content parity: the required
  behavior must exist at the exact pinned revision.
- A freshness check does not establish trust by itself. Test stale evidence and fresh
  evidence from an unapproved source separately, and require abstention (a deliberate
  refusal to answer when evidence cannot support the claim) for both.
- Claim support is a separate contract from source authority. Test supported,
  unsupported, conflicting, and ambiguous claim evidence, and preserve the reason that
  caused abstention.
- Source ingestion must be bounded and ephemeral: process bytes in memory, emit only
  metadata, and keep CI on synthetic fixtures.
- A course-freshness sweep must separate the coordinator from one-course workers,
  enforce course, worker, and elapsed-time limits, persist metadata checkpoints, and
  mark failed or timed-out workers unavailable rather than treating them as clean.
- Course Doctor review packets must preserve one packet per requested course, expose
  reconciled counts, keep claim proposals unverified, and require human adjudication
  before any future content change. Local source adapters must stay root-confined,
  bounded, in-memory, and metadata-only at the output boundary.

## Build path

1. State the evidence contract and the failure that would otherwise pass unnoticed.
2. Reuse the existing evaluator, adapter boundary, and metadata-only report shape.
3. Add the positive control, degraded negative control, and focused tests.
4. Run external reference agents through declarative custom packs when the capability
   needs to prove adapter-boundary behavior; record stable abstention reasons rather
   than relying on a generic refusal.
5. For technical-content assurance, require both source-level controls and claim-level
   controls. An official and fresh source is not sufficient when it does not support the
   declared claim.
6. Route source ingestion through the existing content-assurance contract and test
   oversized, unapproved-host, stale, drifted, and unsupported-claim controls.
7. For a multi-course sweep, fan out only independent course reviews, join before
   aggregating, and test both complete results and lateral worker failure.
8. Turn course findings into review packets without copying source content; test that
   unresolved findings cannot receive an approved adjudication and that failed work
   still emits a not-reviewed packet.
9. Add the control to the blocking CI workflow and preserve the stable
   `Agent reliability gate` job name.
10. For consumer or action changes, run consumer validation, independent provenance
   verification, compatibility verification, and pinned-action content-parity
   verification. The parity check must inspect the immutable Git object, not only the
   current action file.
11. Update `GUIDE.md`, `BUILD_GUIDE.md`, `README.md`, `CLAUDE.md`, and `AGENTS.md` when
   the workflow or repository contract changes.
12. Run the full test suite, repository boundary check, dependency audit, release check,
   lock check, and `git diff --check`.

## Limits

The harness demonstrates enforceable offline controls. It does not establish live model
quality, hosted-runner availability, production authorization state, deployment success,
or signed provenance unless a separate control explicitly proves that property.
