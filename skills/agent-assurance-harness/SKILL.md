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
- Keep the primary showcase deterministic and offline. An optional public-course
  demonstration may use a separately checked-out repository through the root-confined
  local adapter, but never vendor lesson text or export source content.
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
- Claim-proposal workers are untrusted upstream agents. Validate proposal shape,
  identifier uniqueness, source binding, required coverage, and raw-content absence
  before routing proposals to the content pipeline. Invalid proposals must stop
  downstream evaluation and produce a stable reason code.
- Findings must identify the affected claim, section, evidence, source, digest, and
  freshness condition when claim-level checks provide them. Keep any source path or
  line navigation in an explicitly requested local-only index; never put it in a
  public report.
- Reviewer-facing Markdown should translate reason codes into plain-language guidance
  and show where review starts; retain the complete structured representation in JSON.
- The live provider boundary is local-only and opt-in. It must use only fixed official
  endpoints, reject redirects and retries, require request/token/time/spend ceilings,
  and accept only the reviewed identifier-only structured response shape.
- A public-course verifier adapter may reuse a separately checked-out verifier as its
  source of truth, but it must preserve the verifier's evidence tiers and unresolved
  states instead of maintaining a second parser. It must record the checkout revision,
  bounded row/page counts, source URLs, read dates, and safe lesson/claim locators
  without exporting claim text, quotes, source bytes, credentials, or private paths.
- A missing verbatim quote is a human-review signal, not proof of staleness. Identifier
  presence is weaker than claim verification. An offline row inventory is incomplete
  evidence and must not pass.
- An unstructured private draft is not a public fixture. Do not infer timestamps,
  freshness windows, or source locations that the draft does not provide; require a
  separate local-only manifest and human approval before adapting it.
- When the change creates technical enablement content, require a launch-to-field
  pack (a demo, hands-on lab, and quick-reference guide that another person can use)
  with an audience identifier, source contract, freshness state, claim-support state,
  feedback signal, and human-approval boundary. The pack is evidence of a workflow,
  not publication authority.
- Keep role-alignment evidence separate from engineering claims. A portfolio guide may
  map a requirement to a runnable artifact, but it must name what the artifact does
  not prove. Do not turn synthetic counts into claims about live learners, customer
  adoption, deployment success, or general model quality.
- An optional public-course portfolio lane may add a separately checked-out public
  course only through the existing root-confined verifier adapter. Preserve its
  evidence tiers and unresolved states; emit only revision, counts, dates, URLs, and
  safe lesson/claim locators. CI must remain synthetic and offline.
- Public-course review packets may turn those locators into bounded priorities,
  recommended actions, and initial `open` dispositions. They must not include claim
  text, quotations, source bytes, local paths, raw exceptions, or write authority.
- Public-course adjudication must bind every disposition to the exact packet digest and
  course revision. Reject unknown, duplicate, omitted, or free-form decisions; keep
  `adjudicated` separate from technical correctness and publication authority.
- Public-course change plans may carry only safe locations, bounded actions,
  dispositions, and required re-checks. Refuse open, deferred, mismatched, truncated,
  or incomplete state; never emit replacement wording, diffs, file writes, or publish
  authority.
- Public-course post-change verification must require a different course revision,
  compare every planned target, catch new blocking findings, and distinguish verified
  targeted scope from full-course verification. A changed revision alone is not evidence
  that content improved.
- Public repository security hardening must pin external actions to immutable commit
  SHAs, keep workflow permissions least-privilege, lock dependency installation,
  and separate dependency review, static analysis, secret scanning, and supply-chain
  evidence. CODEOWNERS routing is not independent review until the ruleset requires it.

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
9. Add the proposal worker and validator before evidence evaluation; test empty,
   duplicate, fabricated, incomplete, source-drifted, and raw-content-bearing output.
10. Preserve claim-level finding locators through the pipeline and Course Doctor;
    test stale, wrong-source, drift, unsupported, and unavailable-location cases.
11. Add an opt-in local review index for caller-supplied relative paths and optional
    line ranges. Keep it separate from the CI report and test that source paths never
    appear in public output.
12. Add the control to the blocking CI workflow and preserve the stable
   `Agent reliability gate` job name.
13. For consumer or action changes, run consumer validation, independent provenance
   verification, compatibility verification, and pinned-action content-parity
   verification. The parity check must inspect the immutable Git object, not only the
   current action file.
14. Update `GUIDE.md`, `BUILD_GUIDE.md`, `README.md`, `CLAUDE.md`, and `AGENTS.md` when
   the workflow or repository contract changes.
15. Run the full test suite, repository boundary check, dependency audit, release check,
   lock check, and `git diff --check`.
16. Run `uv run python tools/showcase_demo.py --markdown` and verify that the output
    remains offline, metadata-only, and useful to an outside reviewer, including one
    clearly labelled synthetic blocked-finding example.
17. If adapting an existing public verifier, run the full adapter locally against a
    pinned checkout, report evidence tiers separately, inspect every concrete finding,
    and keep the network path outside CI.
18. For launch-to-field enablement, verify that a complete pack contains a demo, lab,
    quick reference, and metadata-only feedback signal. Run at least one ready case
    and degraded stale, wrong-source, unsupported-claim, and incomplete-pack controls.
    A ready result must say that human approval is still required.
19. For instructor development, verify a fixed identifier-only observer rubric covering
    technical accuracy, hands-on execution, live debugging, audience adaptation, and
    the safety boundary. Require feedback metadata, emit coaching recommendations for
    missing behaviors, and keep readiness separate from human sign-off or certification.
20. For a reviewer-facing portfolio orchestrator, define typed lane contracts, run
    independent lanes in parallel, write inspectable metadata-only intermediates, and
    block the join when any required lane is missing or unavailable. Include a negative
    control proving that an incomplete join cannot be presented as ready.
21. For an optional public-course lane, keep the course checkout and fetched source
    bytes behind an explicit local root boundary. Preserve the verifier's evidence
    tiers and unresolved states, include a bounded finding-location summary, and test
    that claim text, quotes, source bytes, local paths, and raw exceptions cannot enter
    the portfolio report.
22. For a public-course review packet, map each concrete evidence state to a stable
    priority and recommended action, bound the number of findings, start every item
    as `open`, and keep human disposition separate from content editing or publication.
23. For public-course adjudication, fingerprint the safe packet, require one bounded
    disposition per known finding, test digest and omission failures, and keep the
    adjudication record separate from content approval or publishing.
24. For a public-course change plan, verify packet and adjudication identity, block open
    or deferred findings, emit a required post-change re-check, and test that no content
    or write capability crosses the boundary.
25. For post-change verification, compare before and after metadata, require revision
    change, test target recovery and new-blocking regressions, and keep the result
    separate from full-course approval or publication.
26. For public repository hardening, pin every external action, enforce the pins in a
    repository boundary check, add dependency-review and CodeQL gates, configure
    Dependabot for Python and Actions, publish Scorecard evidence, and document which
    GitHub settings still require administrator action.

## Limits

The harness demonstrates enforceable offline controls. It does not establish live model
quality, hosted-runner availability, production authorization state, deployment success,
or signed provenance unless a separate control explicitly proves that property.
