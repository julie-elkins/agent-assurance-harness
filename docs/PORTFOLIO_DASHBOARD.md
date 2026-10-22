# Portfolio assurance dashboard

The dashboard is a local static HTML view of a metadata-only portfolio assurance report.
It does not rerun the harness, call a model provider, read credentials, or publish a
report.

“Metadata-only” means the dashboard may show identifiers, states, counts, hashes, and
human-gate text, but not prompts, tool payloads, source text, provider output, or local
source paths.

## Generate it

First create the machine-readable portfolio report:

```bash
uv run python tools/portfolio_assurance_report.py \
  --workspace /tmp/agent-reliability-portfolio \
  --output /tmp/agent-reliability-portfolio.json \
  --fail-on-findings
```

Then render the local dashboard:

```bash
uv run python tools/portfolio_dashboard.py \
  --input /tmp/agent-reliability-portfolio.json \
  --output /tmp/agent-reliability-portfolio.html
```

Open the generated HTML file locally. It has no external JavaScript, CSS, image, or
telemetry dependency.

## What it shows

- the portfolio decision: `ready_for_human_review`, `review_required`, or `blocked`;
- lane status and counts of caught, degraded, and missed controls;
- human approval boundaries for each lane;
- missing and review-required lanes;
- the deliberate missing-lane negative control;
- warnings and explicit limits;
- the source report name and a short SHA-256 fingerprint.

The dashboard derives counts from the validated lists in the input report instead of
trusting caller-supplied totals. If the report is incomplete or contains an unsupported
state, generation refuses and no HTML file is written. That prevents “nothing was
checked” from being rendered as a clean dashboard.

## Deliberate limits

This is not a hosted monitoring dashboard. It shows one bounded run and does not provide
alerting, historical storage, authentication, live provider telemetry, or incident
response. A `ready_for_human_review` result is a handoff state, not approval to publish,
release, or certify an outcome.
