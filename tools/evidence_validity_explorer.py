"""Render a local before-and-after view of run-manifest evidence validity.

The explorer is a presentation layer over the canonical run-manifest evaluator:

1. Load one metadata-only manifest and two revision maps.
2. Evaluate both maps with the existing reauthorization rule.
3. Render only bounded identifiers, decisions, and safe usage metadata.

It never runs a provider, reads credentials, stores evidence content, or replaces the
decision source. The changed revision map is a deliberate negative control: a known
change that should prevent silent reuse of the earlier result.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agent_reliability_lab.evidence_provenance import (
    EvidenceProvenanceDecision,
    EvidenceValidityMetadata,
    evaluate_evidence_provenance,
)
from agent_reliability_lab.run_manifest import (
    REQUIRED_REVISION_KEYS,
    ReauthorizationDecision,
    RunManifest,
    evaluate_reauthorization,
    load_current_revisions,
    load_manifest,
)


@dataclass(frozen=True)
class ExplorerData:
    """The validated, metadata-only data needed by the explorer."""

    manifest: RunManifest
    current_revisions: dict[str, str]
    changed_revisions: dict[str, str]
    current_decision: ReauthorizationDecision
    changed_decision: ReauthorizationDecision
    current_provenance_decision: EvidenceProvenanceDecision | None = None
    missing_provenance_decision: EvidenceProvenanceDecision | None = None

    @classmethod
    def from_inputs(
        cls,
        manifest: RunManifest,
        current_revisions: Mapping[str, str],
        changed_revisions: Mapping[str, str],
        current_provenance: Mapping[str, object] | None = None,
        missing_provenance: Mapping[str, object] | None = None,
    ) -> "ExplorerData":
        if (current_provenance is None) != (missing_provenance is None):
            raise ValueError(
                "current_provenance and missing_provenance must be supplied together."
            )
        current = dict(current_revisions)
        changed = dict(changed_revisions)
        current_decision = evaluate_reauthorization(manifest, current)
        changed_decision = evaluate_reauthorization(manifest, changed)
        current_provenance_decision = (
            evaluate_evidence_provenance(manifest, current_provenance)
            if current_provenance is not None
            else None
        )
        missing_provenance_decision = (
            evaluate_evidence_provenance(manifest, missing_provenance)
            if missing_provenance is not None
            else None
        )
        return cls(
            manifest=manifest,
            current_revisions=current,
            changed_revisions=changed,
            current_decision=current_decision,
            changed_decision=changed_decision,
            current_provenance_decision=current_provenance_decision,
            missing_provenance_decision=missing_provenance_decision,
        )


def render_explorer(
    data: ExplorerData,
    *,
    manifest_name: str,
    current_name: str,
    changed_name: str,
) -> str:
    """Render a self-contained HTML explorer from validated metadata."""

    manifest = data.manifest
    changed_keys = set(data.changed_decision.changed_dependencies)
    revision_rows = "\n".join(
        _render_revision_row(
            key,
            manifest.revisions[key],
            data.current_revisions[key],
            data.changed_revisions[key],
            key in changed_keys,
        )
        for key in REQUIRED_REVISION_KEYS
    )
    changed_tokens = _render_tokens(
        data.changed_decision.changed_dependencies,
        empty="No dependency revision changed",
    )
    current_reasons = _render_tokens(
        data.current_decision.reasons,
        empty="None",
    )
    changed_reasons = _render_tokens(
        data.changed_decision.reasons,
        empty="None",
    )
    current_action = _escape(data.current_decision.required_action)
    changed_action = _escape(data.changed_decision.required_action)
    current_status = _status_label(data.current_decision.status)
    changed_status = _status_label(data.changed_decision.status)
    current_class = _status_class(data.current_decision.status)
    changed_class = _status_class(data.changed_decision.status)
    provenance_story = ""
    if (
        data.current_provenance_decision is not None
        and data.missing_provenance_decision is not None
    ):
        provenance_story = _render_provenance_story(
            current=data.current_provenance_decision,
            changed=data.changed_decision,
            missing=data.missing_provenance_decision,
        )
    validity_metadata = ""
    if (
        data.current_provenance_decision is not None
        and data.current_provenance_decision.validity_metadata is not None
    ):
        validity_metadata = _render_validity_metadata(
            data.current_provenance_decision.validity_metadata
        )
    source_fingerprint = _escape(
        hashlib.sha256(
            json.dumps(
                manifest.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
    )
    manifest_label = _escape(Path(manifest_name).name)
    current_label = _escape(Path(current_name).name)
    changed_label = _escape(Path(changed_name).name)
    changed_count = len(data.changed_decision.changed_dependencies)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Evidence Validity Explorer</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #182338;
      --muted: #5a6780;
      --line: #d8e0ec;
      --surface: #ffffff;
      --background: #f4f7fb;
      --accent: #2457a6;
      --accent-soft: #e8f0ff;
      --green: #126b50;
      --green-soft: #e3f5ee;
      --amber: #8a5b00;
      --amber-soft: #fff3cf;
      --red: #a03d45;
      --red-soft: #fbe7e9;
      --code: #edf2f8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top right, #e6efff 0, transparent 31rem),
        var(--background);
      color: var(--ink);
      font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ max-width: 1160px; margin: 0 auto; padding: 42px 24px 64px; }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(2.1rem, 5vw, 3.7rem); letter-spacing: -0.045em; line-height: 1.05; }}
    h2 {{ font-size: 1.25rem; line-height: 1.2; }}
    h3 {{ font-size: 1rem; line-height: 1.25; }}
    code {{
      background: var(--code);
      border-radius: 5px;
      color: #34445f;
      font: 0.86em ui-monospace, SFMono-Regular, Menlo, monospace;
      padding: 2px 5px;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 0.76rem;
      font-weight: 800;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    .hero {{
      align-items: end;
      display: flex;
      gap: 26px;
      justify-content: space-between;
    }}
    .hero-copy {{ max-width: 720px; }}
    .hero-copy p + h1 {{ margin-top: 10px; }}
    .lede {{ color: var(--muted); font-size: 1.08rem; margin-top: 17px; max-width: 680px; }}
    .hero-status {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      min-width: 245px;
      padding: 17px 19px;
    }}
    .hero-status .label {{ color: var(--muted); font-size: 0.82rem; }}
    .hero-status strong {{ display: block; font-size: 1.25rem; margin-top: 4px; }}
    .status {{
      border-radius: 999px;
      display: inline-block;
      font-size: 0.74rem;
      font-weight: 800;
      letter-spacing: 0.07em;
      padding: 4px 9px;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .status--reauthorized {{ background: var(--green-soft); color: var(--green); }}
    .status--review {{ background: var(--amber-soft); color: var(--amber); }}
    .status--blocked {{ background: var(--red-soft); color: var(--red); }}
    .summary {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin: 30px 0 18px;
    }}
    .metric, .panel, .scenario {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 15px;
    }}
    .metric {{ padding: 16px; }}
    .metric-label {{ color: var(--muted); font-size: 0.84rem; }}
    .metric-value {{ font-size: 1.75rem; font-weight: 800; margin-top: 5px; }}
    .panel {{ margin-top: 16px; padding: 23px; }}
    .panel-heading {{
      align-items: baseline;
      display: flex;
      gap: 12px;
      justify-content: space-between;
      margin-bottom: 16px;
    }}
    .panel-heading p {{ color: var(--muted); font-size: 0.88rem; }}
    .scenario-grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .scenario {{ padding: 19px; }}
    .scenario--current {{ border-top: 4px solid var(--green); }}
    .scenario--changed {{ border-top: 4px solid var(--amber); }}
    .story-grid {{
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }}
    .story-step {{
      background: var(--background);
      border: 1px solid var(--line);
      border-radius: 12px;
      min-height: 145px;
      padding: 15px;
      position: relative;
    }}
    .story-step::after {{
      color: var(--muted);
      content: "→";
      font-size: 1.3rem;
      position: absolute;
      right: -9px;
      top: 56px;
      z-index: 1;
    }}
    .story-step:last-child::after {{ content: ""; }}
    .story-step--observed {{ border-top: 4px solid var(--green); }}
    .story-step--review {{ border-top: 4px solid var(--amber); }}
    .story-step--missing {{ border-top: 4px solid var(--red); }}
    .story-number {{
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .story-title {{ font-size: 0.98rem; font-weight: 800; margin-top: 7px; }}
    .story-status {{ margin-top: 10px; }}
    .story-action {{ color: var(--muted); font-size: 0.82rem; margin-top: 10px; }}
    .story-caption {{ color: var(--muted); font-size: 0.86rem; margin-top: 16px; }}
    .scenario-header {{
      align-items: start;
      display: flex;
      gap: 12px;
      justify-content: space-between;
    }}
    .scenario-title {{ font-size: 1.1rem; font-weight: 800; }}
    .scenario-caption {{ color: var(--muted); font-size: 0.84rem; margin-top: 3px; }}
    .action {{
      border-left: 3px solid var(--line);
      color: var(--ink);
      margin-top: 17px;
      padding-left: 12px;
    }}
    .action strong {{ display: block; font-size: 0.82rem; margin-bottom: 3px; }}
    .token-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      list-style: none;
      margin: 11px 0 0;
      padding: 0;
    }}
    .token {{
      background: var(--code);
      border-radius: 6px;
      color: #34445f;
      font: 0.8rem ui-monospace, SFMono-Regular, Menlo, monospace;
      padding: 4px 7px;
    }}
    .quiet {{ color: var(--muted); }}
    .comparison {{ overflow-x: auto; }}
    table {{ border-collapse: collapse; min-width: 720px; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 11px 10px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 0.8rem; font-weight: 700; }}
    td {{ font-size: 0.88rem; }}
    tr:last-child td {{ border-bottom: 0; }}
    .revision-name {{ font-weight: 800; }}
    .revision-state {{ font-weight: 800; }}
    .revision-state--same {{ color: var(--green); }}
    .revision-state--changed {{ color: var(--amber); }}
    .limits {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 14px;
    }}
    .limit {{ background: #f8faff; border-left: 3px solid var(--accent); padding: 12px 14px; }}
    .limit-label {{ color: var(--muted); font-size: 0.8rem; }}
    .limit-value {{ font-weight: 800; margin-top: 2px; }}
    .boundary {{
      background: var(--accent-soft);
      border: 1px solid #cbdcff;
      color: #273d68;
    }}
    .boundary p + p {{ margin-top: 10px; }}
    .meta {{ color: var(--muted); font-size: 0.8rem; margin-top: 26px; }}
    footer {{ border-top: 1px solid var(--line); color: var(--muted); font-size: 0.84rem; margin-top: 28px; padding-top: 18px; }}
    @media (max-width: 780px) {{
      main {{ padding: 30px 16px 48px; }}
      .hero, .panel-heading {{ align-items: start; display: block; }}
      .hero-status {{ margin-top: 18px; }}
      .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .scenario-grid, .limits {{ grid-template-columns: 1fr; }}
      .story-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .story-step::after {{ content: ""; }}
      .panel-heading p {{ margin-top: 6px; }}
    }}
    @media (max-width: 480px) {{
      .story-grid {{ grid-template-columns: 1fr; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      main {{ padding: 0; }}
      .hero-status, .metric, .panel, .scenario {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <main aria-labelledby="page-title">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Agent Assurance Harness</p>
        <h1 id="page-title">Can this evidence still support the decision?</h1>
        <p class="lede">A before-and-after view of one bounded evidence record. The
        evidence is reusable only while the model, harness, prompt, tools, policy, data,
        repository, environment, and grader revisions remain bound to the declared scope.</p>
      </div>
      <div class="hero-status" aria-label="Current evidence decision">
        <span class="label">Current evidence</span>
        <strong><span class="status {current_class}">{_escape(current_status)}</span></strong>
      </div>
    </section>

    <section class="summary" aria-label="Explorer summary">
      {_metric("Declared target", manifest.decision_target)}
      {_metric("Changed revisions", str(changed_count))}
      {_metric("Repeat count", str(manifest.repeatability.run_count))}
      {_metric("Observed outcome", manifest.observed_outcome)}
    </section>

    {provenance_story}

    {validity_metadata}

    <section class="panel" aria-labelledby="decision-heading">
      <div class="panel-heading">
        <h2 id="decision-heading">The decision changes when the dependency changes</h2>
        <p>Same manifest · two revision snapshots</p>
      </div>
      <div class="scenario-grid">
        <article class="scenario scenario--current">
          <div class="scenario-header">
            <div>
              <p class="scenario-title">Recorded state</p>
              <p class="scenario-caption">{current_label}</p>
            </div>
            <span class="status {current_class}">{_escape(current_status)}</span>
          </div>
          <p class="action"><strong>What happens next</strong>{current_action}</p>
          <p class="scenario-caption" style="margin-top: 15px">Reasons</p>
          {current_reasons}
        </article>
        <article class="scenario scenario--changed">
          <div class="scenario-header">
            <div>
              <p class="scenario-title">After a revision change</p>
              <p class="scenario-caption">{changed_label}</p>
            </div>
            <span class="status {changed_class}">{_escape(changed_status)}</span>
          </div>
          <p class="action"><strong>What happens next</strong>{changed_action}</p>
          <p class="scenario-caption" style="margin-top: 15px">Reasons</p>
          {changed_reasons}
        </article>
      </div>
      <h3 style="margin-top: 22px">Changed dependencies</h3>
      {changed_tokens}
    </section>

    <section class="panel" aria-labelledby="revisions-heading">
      <div class="panel-heading">
        <h2 id="revisions-heading">Revision binding</h2>
        <p>Values are identifiers, not prompts or provider output</p>
      </div>
      <div class="comparison">
        <table>
          <thead>
            <tr>
              <th scope="col">Dependency</th>
              <th scope="col">Evidence recorded</th>
              <th scope="col">Current state</th>
              <th scope="col">Changed example</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>{revision_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="panel" aria-labelledby="bounds-heading">
      <div class="panel-heading">
        <h2 id="bounds-heading">What the manifest carries</h2>
        <p>{_escape(manifest.provider)} · {_escape(manifest.model)}</p>
      </div>
      <div class="limits">
        {_limit("Budget", f"{manifest.budget.requests}/{manifest.budget.max_requests} requests")}
        {_limit("Repeatability", f"{manifest.repeatability.successful_run_count}/{manifest.repeatability.run_count} successful")}
        {_limit("Evidence expiry", manifest.evidence_expires_at or "not declared")}
        {_limit("Evidence scope", ", ".join(manifest.evidence_scope))}
      </div>
    </section>

    <section class="panel boundary" aria-labelledby="boundary-heading">
      <h2 id="boundary-heading">What this does—and does not—prove</h2>
      <p style="margin-top: 12px">It shows whether the same metadata-bound evidence
      still supports its declared decision after a dependency revision changes.</p>
      <p>It does not prove live model quality, production safety, business impact,
      or that a human has approved the next action.</p>
    </section>

    <p class="meta">Manifest: <code>{manifest_label}</code> · Manifest fingerprint:
    <code>{source_fingerprint}</code> · This page is local, synthetic, and metadata-only.</p>
    <footer>Evidence validity is a decision boundary, not a score. A changed result
    requires an explicit rerun and reauthorization decision.</footer>
  </main>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    """Render the explorer to one explicitly requested local HTML file."""

    parser = argparse.ArgumentParser(
        description=(
            "Render a local metadata-only before-and-after view of "
            "run-manifest evidence validity."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--changed-revisions", type=Path, required=True)
    parser.add_argument(
        "--provenance",
        type=Path,
        help="Synthetic observed-evidence producer record for the story view.",
    )
    parser.add_argument(
        "--missing-provenance",
        type=Path,
        help="Synthetic missing-evidence negative control for the story view.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        data = ExplorerData.from_inputs(
            load_manifest(str(args.manifest)),
            load_current_revisions(str(args.current_revisions)),
            load_current_revisions(str(args.changed_revisions)),
            current_provenance=(
                _load_object(args.provenance)
                if args.provenance is not None
                else None
            ),
            missing_provenance=(
                _load_object(args.missing_provenance)
                if args.missing_provenance is not None
                else None
            ),
        )
        rendered = render_explorer(
            data,
            manifest_name=args.manifest.name,
            current_name=args.current_revisions.name,
            changed_name=args.changed_revisions.name,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "error": "evidence_validity_explorer_refused",
                    "message": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(f"explorer written to {args.output}", file=sys.stderr)
    return 0


def _load_object(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def _render_provenance_story(
    *,
    current: EvidenceProvenanceDecision,
    changed: ReauthorizationDecision,
    missing: EvidenceProvenanceDecision,
) -> str:
    return f"""
    <section class="panel" aria-labelledby="story-heading">
      <div class="panel-heading">
        <h2 id="story-heading">The five-minute assurance story</h2>
        <p>One result · four visible control states</p>
      </div>
      <div class="story-grid">
        {_story_step(
            "1",
            "Evidence observed",
            current.status,
            "The producer record is bound to this manifest.",
            "story-step--observed",
        )}
        {_story_step(
            "2",
            "A revision changes",
            changed.status,
            "The prompt and tool revisions no longer match.",
            "story-step--review",
        )}
        {_story_step(
            "3",
            "Reuse requires review",
            changed.status,
            "The earlier result cannot be silently reused.",
            "story-step--review",
        )}
        {_story_step(
            "4",
            "Evidence is missing",
            missing.status,
            "Reuse is blocked until a producer records evidence.",
            "story-step--missing",
        )}
      </div>
      <p class="story-caption">The page shows decision metadata only. It does not
      inspect or publish traces, transcripts, prompts, tool payloads, credentials, or
      provider output.</p>
    </section>
    """


def _render_validity_metadata(metadata: EvidenceValidityMetadata) -> str:
    values = metadata.to_dict()
    return f"""
    <section class="panel" aria-labelledby="validity-heading">
      <div class="panel-heading">
        <h2 id="validity-heading">Metadata an evaluator can inspect safely</h2>
        <p>Receipt · grader · synthetic deployment context</p>
      </div>
      <div class="limits">
        {_limit("Receipt", f"{values['artifact_type']} · {values['producer_version']}")}
        {_limit("Capture scope", values["capture_scope"])}
        {_limit("Retention", values["retention_status"])}
        {_limit("Grader", f"{values['grader_type']} · {values['grader_calibration_status']}")}
        {_limit("Independent breaker", values["independent_breaker_id"])}
        {_limit("Sample count", values["sample_count"])}
        {_limit("Scenario source", values["scenario_source"])}
        {_limit("Trajectory horizon", values["trajectory_horizon"])}
        {_limit("Tool risk tier", values["tool_risk_tier"])}
      </div>
      <p class="story-caption">These are identifiers, counts, timestamps, and status
      values only. The page does not expose the evidence artifact itself.</p>
    </section>
    """


def _story_step(
    number: str,
    title: str,
    status: str,
    action: str,
    class_name: str,
) -> str:
    return f"""
    <article class="story-step {class_name}">
      <p class="story-number">Step {number}</p>
      <h3 class="story-title">{_escape(title)}</h3>
      <p class="story-status"><span class="status {_status_class(status)}">
      {_escape(_status_label(status))}</span></p>
      <p class="story-action">{_escape(action)}</p>
    </article>
    """


def _metric(label: str, value: object) -> str:
    return (
        '<div class="metric">'
        f'<p class="metric-label">{_escape(label)}</p>'
        f'<p class="metric-value">{_escape(value)}</p>'
        "</div>"
    )


def _limit(label: str, value: object) -> str:
    return (
        '<div class="limit">'
        f'<p class="limit-label">{_escape(label)}</p>'
        f'<p class="limit-value">{_escape(value)}</p>'
        "</div>"
    )


def _render_revision_row(
    key: str,
    recorded: str,
    current: str,
    changed: str,
    changed_flag: bool,
) -> str:
    state_label = "changed" if changed_flag else "same"
    state_class = "revision-state--changed" if changed_flag else "revision-state--same"
    return f"""<tr>
  <th scope="row" class="revision-name">{_escape(key)}</th>
  <td><code>{_escape(recorded)}</code></td>
  <td><code>{_escape(current)}</code></td>
  <td><code>{_escape(changed)}</code></td>
  <td><span class="revision-state {state_class}">{state_label}</span></td>
</tr>"""


def _render_tokens(values: tuple[str, ...], *, empty: str) -> str:
    if not values:
        return f'<p class="quiet" style="margin-top: 11px">{_escape(empty)}</p>'
    items = "".join(
        f'<li class="token">{_escape(value)}</li>' for value in values
    )
    return f'<ul class="token-list">{items}</ul>'


def _status_label(status: str) -> str:
    return status.replace("_", " ")


def _status_class(status: str) -> str:
    if status == "reauthorized":
        return "status--reauthorized"
    if status == "reauthorization_required":
        return "status--review"
    return "status--blocked"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
