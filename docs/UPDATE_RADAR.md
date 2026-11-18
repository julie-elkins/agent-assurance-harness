# Update radar

The update radar is a bounded, read-only review workflow for keeping public
courses and design guides current.

An **update radar** finds source changes and review leads. It does not decide
that a course is stale, rewrite content, approve a change, or publish a PR.
Human adjudication remains the approval boundary.

## Evidence tiers

| Tier | Source | Meaning |
| --- | --- | --- |
| confirmed | Official documentation, changelog, standard, or first-party cookbook | Strongest lead; still requires checking scope and affected files |
| candidate | Official course, research paper, or maintained reference implementation | Useful design input; verify before changing learner claims |
| lead | A queued LinkedIn post or other social post | Discovery signal only; never a source of truth by itself |

The source registry is
[`examples/update-radar/source-registry.json`](../examples/update-radar/source-registry.json).
It maps sources to affected repositories and records whether the existing
metadata-only refresher can hash the source or whether a person must review it
through the official site.

## Safe workflow

1. Refresh the fixed official sources with
   `tools/refresh_public_sources.py`.
2. Compare the new metadata manifest with the previous manifest.
3. Add any LinkedIn post to an explicitly reviewed inbox file; do not scrape the
   signed-in feed or collect unrelated private-feed content.
4. Run `tools/update_radar_report.py` to produce a metadata-only worklist.
5. Verify a changed source and map it to the affected lesson, guide, or repo.
6. Record a human disposition before creating a content change.
7. Rebuild, test, and review the changed repository as a normal pull request.

## Manual-source review checklist

Sources marked `manual_official_review` are intentionally not auto-approved
from a page hash. For each one, record:

- the source URL and retrieval date;
- the current workflow or terminology that changed;
- the affected course claim, lesson, guide, or implementation reference;
- whether the change is `update_needed`, `no_change`, or
  `not_evaluated`;
- the evidence that supports the disposition; and
- the human owner who approved or deferred the change.

For provider-specific evaluation tools, also record the evaluator scope:
final response, single step, trajectory, or thread/session. A tool name or
green dashboard is not enough to establish evaluator validity.

The current public course uses provider-neutral evidence contracts. Provider
references such as Codex, Promptfoo, LangSmith, and OpenTelemetry are optional
implementation mappings and must not silently become required dependencies.

## Commands

```bash
uv run python tools/refresh_public_sources.py \
  --output /tmp/public-sources-current.json \
  --markdown

uv run python tools/update_radar_report.py \
  --registry examples/update-radar/source-registry.json \
  --current /tmp/public-sources-current.json \
  --previous /tmp/public-sources-previous.json \
  --inbox /tmp/update-radar-inbox.json \
  --output /tmp/update-radar-report.json \
  --markdown
```

The inbox is optional. A queued item should contain only the URL, a human
supplied label, and its intended review scope:

```json
{
  "items": [
    {
      "item_id": "linkedin-2026-11-05-001",
      "url": "https://lnkd.in/example",
      "label": "Candidate memory-evaluation update",
      "scope": ["claude-evaluation-lab"],
      "trust_tier": "lead"
    }
  ]
}
```

The report preserves `not_evaluated` when a source lacks a current digest or
when an inbox item has not been verified. A missing source result cannot become
a green “no changes” result.

## What this does not prove

An unchanged page hash does not prove that the course claim remains correct in
every context. A changed hash does not prove that a course update is required.
The radar identifies where a person should begin review; it does not replace
reading the source, checking the affected claim, or approving the change.
