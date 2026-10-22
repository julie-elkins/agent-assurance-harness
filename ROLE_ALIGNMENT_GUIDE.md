# Portfolio Evidence Guide

This guide maps the public Agent Assurance Harness to the technical education,
developer experience, and enablement work described in the Anthropic and OpenAI
roles reviewed on 2026-10-22.

It is an evidence map, not a claim that a synthetic repository proves employment
history or live production outcomes. Each row points to something a reviewer can
inspect or run.

## The short reviewer path

Run the showcase first:

```bash
uv sync --extra dev
uv run python tools/showcase_demo.py --markdown
```

Then run the launch-to-field pack directly:

```bash
uv run python tools/launch_to_field_report.py \
  --markdown \
  --fail-on-findings
```

The launch-to-field pack is a synthetic, offline workflow that turns one changing
technical capability into a demo, hands-on lab, and quick-reference guide. It
checks source authority, freshness, claim support, asset completeness, and
feedback metadata before marking the pack ready for human approval.

For the shortest combined reviewer path, run:

```bash
uv run python tools/portfolio_assurance_report.py \
  --workspace /tmp/agent-reliability-portfolio \
  --markdown \
  --fail-on-findings
```

This joins agent assurance, Course Doctor, launch-to-field enablement, instructor
calibration, and production delivery evidence. It is a reviewer handoff, not proof of
live production impact or employment history.

To demonstrate the same portfolio against the public Claude course, add:

```bash
uv run python tools/portfolio_assurance_report.py \
  --course-root /path/to/claude-architect-lab \
  --course-id claude-architect-lab \
  --workspace /tmp/agent-assurance-public-course-portfolio \
  --markdown \
  --max-rows 1000 \
  --max-requests 50
```

The optional lane makes the course revision, evidence tiers, and safe finding locations
visible. A `review_required` result is evidence that the system preserved uncertainty;
it is not a claim that every course row is incorrect.

## Requirement-to-evidence map

| Capability a reviewer needs to see | Public evidence | What it demonstrates |
| --- | --- | --- |
| Production-quality code | `src/`, `tests/`, CI, release checks | The project has a maintained implementation and a repeatable delivery path. |
| AI agents and tool use | `src/agent_reliability_lab/`, synthetic adapters, MCP server | Agent behavior is evaluated through explicit evidence rather than answer quality alone. |
| Responsible AI controls | Evidence contracts, abstention, authorization, privacy boundaries | Unsafe or unsupported behavior becomes a blocked result instead of a polished answer. |
| Technical courses and labs | `claude-architect-lab` and the Course Doctor workflow | Technical content can be structured, checked, and routed for human approval. |
| Content-freshness automation | Course Doctor, source fingerprints, stale and wrong-source controls | A changing source can block outdated material before publication. |
| Launch-ready enablement | `tools/launch_to_field_report.py` and `enablement_pack.py` | One workflow produces the metadata contract for a demo, lab, quick reference, and feedback loop. |
| Self-service resources | CLI tools, `SHOWCASE.md`, `GUIDE.md`, reusable skill | Another engineer can run the workflow without the author in the room. |
| Fast iteration | Deterministic fixtures, focused negative controls, provider-neutral boundaries | New capabilities can be added without waiting for provider credentials or live network state. |
| Instructor quality | `tools/instructor_calibration_report.py` and the observer rubric | Missing teaching behaviors become coaching recommendations, while readiness remains a human sign-off decision. |
| Reviewer-facing orchestration | `tools/portfolio_assurance_report.py` and inspectable lane reports | Independent evidence paths join into one report while missing or unavailable work remains blocking. |
| Public technical-content evidence | Optional `--course-root` lane using `claude_course_adapter.py` | A real public course can be reviewed through the same metadata boundary without being copied into the harness. |
| Actionable content review | `tools/public_course_review_packet.py` | Concrete findings become a bounded human worklist with priorities and next actions, without auto-publishing changes. |
| Human review decision boundary | `tools/public_course_review_adjudication.py` | Binds explicit dispositions to the exact packet revision while preserving the separate approval and publication boundary. |
| Safe change planning | `tools/public_course_change_plan.py` | Converts dispositioned findings into re-checkable maintenance proposals without copying content or granting write authority. |
| Post-change verification | `tools/public_course_post_change.py` | Proves the planned scope recovered on a new revision and catches new blocking findings without claiming full-course correctness. |
| Supply-chain hardening | `.github/workflows/`, `dependabot.yml`, CodeQL, Scorecard | Demonstrates immutable CI dependencies, dependency-change review, static analysis, and public security evidence. |
| Honest review ownership | `.github/CODEOWNERS` and `SECURITY.md` | Shows review routing and clearly states when independent approval does and does not exist. |
| Feedback to product or content owners | Synthetic feedback signals in the launch pack | Usage signals can lead to a documented retain, clarify, revise, or retire action. |
| Portfolio ownership | Public guides, tests, runnable examples, and limitations | The work is inspectable rather than represented only by a résumé bullet. |

## Current limits

The repository does not by itself prove:

- the number of live learners taught;
- live customer or seller adoption;
- a production deployment;
- semantic truth of a documentation source;
- general live-model reliability; or
- an instructor's performance in a real classroom.

Those claims require separate evidence such as delivered sessions, public talks,
learner feedback, or production telemetry. The repository is deliberately honest
about that boundary because overstating synthetic evidence weakens the portfolio.

## What the combined report adds

The report makes the complete path visible from one command:

1. Agent behavior is checked against evidence and negative controls.
2. Course findings become review packets with reconciled counts.
3. A demo, lab, and quick reference are evaluated as one enablement pack.
4. Instructor observations become coaching or human-sign-off recommendations.
5. Delivery-path artifacts remain visible without claiming deployment success.
6. A missing lane blocks the joined handoff rather than disappearing from the summary.

The reusable patterns behind this path live in the
[`agent-systems-design-guide`](https://github.com/julie-elkins/agent-systems-design-guide).
The MCP-specific contract remains in the
[`mcp-server-design-guide`](https://github.com/julie-elkins/mcp-server-design-guide).

## Role sources

- [Anthropic Lead Technical Instructor](https://job-boards.greenhouse.io/anthropic/jobs/5415537008)
- [Anthropic Developer Education Lead, Claude Platform](https://job-boards.greenhouse.io/anthropic/jobs/5311465008)
- [OpenAI Developer Experience Engineer](https://openai.com/careers/developer-experience-engineer-san-francisco/)
- [OpenAI GTM Technical Onboarding Program Manager](https://openai.com/careers/gtm-technical-onboarding-program-manager-san-francisco/)
- [OpenAI Solutions Engineer, Education](https://openai.com/careers/solutions-engineer-education-new-york-city/)
- [OpenAI Software Engineer, Native Learning Experiences](https://openai.com/careers/software-engineer-native-learning-experiences-san-francisco/)
