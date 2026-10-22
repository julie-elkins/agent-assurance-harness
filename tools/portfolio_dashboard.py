"""Render a safe local dashboard from a portfolio assurance report.

Design rules:

1. Read only the metadata-only portfolio report; never rerun a lane or provider.
2. Validate the fields this view uses before rendering; incomplete input is a refusal.
3. Render only whitelisted fields and escape every value placed in HTML.
4. Keep the output local and dependency-free; a dashboard is a review surface, not a
   hosted service or a second evaluator.
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


_DECISIONS = frozenset(
    {"ready_for_human_review", "review_required", "blocked"}
)
_LANE_STATUSES = frozenset(
    {"passed", "blocked", "review_required", "unavailable"}
)


@dataclass(frozen=True)
class DashboardLane:
    """The safe subset of one portfolio lane used by the dashboard."""

    lane_id: str
    title: str
    status: str
    controls_caught: int
    controls_missed: tuple[str, ...]
    degraded_controls: int
    human_gate: str
    reason_code: str | None


@dataclass(frozen=True)
class DashboardNegativeControl:
    """The safe result of the missing-lane orchestration control."""

    control_id: str
    caught: bool
    observed_decision: str
    reason_code: str


@dataclass(frozen=True)
class DashboardReport:
    """The validated, metadata-only view model for the HTML dashboard."""

    decision: str
    passed: bool
    lanes: tuple[DashboardLane, ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]
    missing_lanes: tuple[str, ...]
    review_required_lanes: tuple[str, ...]
    negative_control: DashboardNegativeControl
    warnings: tuple[str, ...]
    what_it_does_not_show: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> DashboardReport:
        """Validate a portfolio report and retain only dashboard-safe metadata."""

        decision = _required_text(value, "decision")
        if decision not in _DECISIONS:
            raise ValueError(f"Unsupported portfolio decision: {decision!r}.")
        passed = value.get("passed")
        if not isinstance(passed, bool):
            raise ValueError("Portfolio report field 'passed' must be boolean.")
        if passed != (decision == "ready_for_human_review"):
            raise ValueError(
                "Portfolio report fields 'passed' and 'decision' disagree."
            )

        raw_lanes = value.get("lanes")
        if not isinstance(raw_lanes, list) or not raw_lanes:
            raise ValueError("Portfolio report must contain a non-empty 'lanes' list.")
        lanes = tuple(_lane_from_dict(item) for item in raw_lanes)

        negative_control = _negative_control_from_dict(
            _required_object(value, "negative_control")
        )
        diagnostics = _required_object(value, "diagnostics")
        warnings = _string_list(diagnostics, "warnings")
        what_it_does_not_show = _required_text(
            diagnostics,
            "what_it_does_not_show",
        )

        return cls(
            decision=decision,
            passed=passed,
            lanes=lanes,
            controls_caught=_string_list(value, "controls_caught"),
            controls_missed=_string_list(value, "controls_missed"),
            missing_lanes=_string_list(value, "missing_lanes"),
            review_required_lanes=_string_list(value, "review_required_lanes"),
            negative_control=negative_control,
            warnings=warnings,
            what_it_does_not_show=what_it_does_not_show,
        )


def render_dashboard(
    report: DashboardReport,
    *,
    source_name: str,
    report_sha256: str,
) -> str:
    """Render a self-contained dashboard from validated metadata."""

    lane_cards = "\n".join(_render_lane(lane) for lane in report.lanes)
    caught_controls = _render_tokens(report.controls_caught, empty="None caught")
    missed_controls = _render_tokens(report.controls_missed, empty="None")
    missing_lanes = _render_tokens(report.missing_lanes, empty="None")
    review_lanes = _render_tokens(
        report.review_required_lanes,
        empty="None",
    )
    warning_items = "\n".join(
        f"<li>{_escape(item)}</li>" for item in report.warnings
    )
    negative_status = "CAUGHT" if report.negative_control.caught else "MISSED"
    negative_class = (
        "status--passed"
        if report.negative_control.caught
        else "status--blocked"
    )
    decision_label = report.decision.replace("_", " ")
    decision_class = _decision_class(report.decision)
    source_label = _escape(Path(source_name).name)
    report_hash = _escape(report_sha256[:16])

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Assurance portfolio dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172033;
      --muted: #5b667a;
      --line: #d9e0ea;
      --surface: #ffffff;
      --background: #f4f7fb;
      --blue: #2457a6;
      --green: #13795b;
      --amber: #9a6500;
      --red: #a13d3d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--background);
      color: var(--ink);
      font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 42px 24px 60px; }}
    h1, h2, h3 {{ line-height: 1.2; margin: 0; }}
    h1 {{ font-size: clamp(2rem, 4vw, 3rem); letter-spacing: -0.03em; }}
    h2 {{ font-size: 1.25rem; margin-bottom: 16px; }}
    h3 {{ font-size: 1.05rem; }}
    p {{ margin: 0; }}
    .eyebrow {{
      color: var(--blue);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .intro {{ display: flex; justify-content: space-between; gap: 24px; align-items: end; }}
    .intro-copy {{ max-width: 760px; }}
    .subtitle {{ color: var(--muted); margin-top: 12px; }}
    .decision {{
      border: 1px solid var(--line);
      border-radius: 14px;
      min-width: 220px;
      padding: 16px 18px;
      background: var(--surface);
    }}
    .decision-label {{ color: var(--muted); font-size: 0.8rem; }}
    .decision-value {{ font-size: 1.15rem; font-weight: 700; margin-top: 4px; }}
    .decision--pass {{ border-color: #9bd5bd; }}
    .decision--review {{ border-color: #e8c979; }}
    .decision--blocked {{ border-color: #e0a6a6; }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 28px 0;
    }}
    .metric, .panel, .lane {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
    }}
    .metric {{ padding: 16px; }}
    .metric-label {{ color: var(--muted); font-size: 0.85rem; }}
    .metric-value {{ font-size: 1.8rem; font-weight: 700; margin-top: 5px; }}
    .panel {{ padding: 22px; margin-top: 16px; }}
    .lane-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .lane {{ padding: 18px; }}
    .lane-header {{ display: flex; justify-content: space-between; gap: 12px; align-items: start; }}
    .lane-id {{ color: var(--muted); font-size: 0.82rem; margin-top: 3px; }}
    .status {{
      border-radius: 999px;
      display: inline-block;
      font-size: 0.74rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      padding: 4px 9px;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .status--passed {{ background: #e2f5ed; color: var(--green); }}
    .status--review {{ background: #fff4d3; color: var(--amber); }}
    .status--blocked, .status--unavailable {{ background: #fbe7e7; color: var(--red); }}
    .lane-stats {{ display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 18px 0; }}
    .lane-stat {{ color: var(--muted); font-size: 0.86rem; }}
    .lane-stat strong {{ color: var(--ink); }}
    .gate {{ border-top: 1px solid var(--line); color: var(--muted); font-size: 0.88rem; padding-top: 12px; }}
    .columns {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .token-list {{ display: flex; flex-wrap: wrap; gap: 7px; list-style: none; margin: 0; padding: 0; }}
    .token {{ background: #edf2f8; border-radius: 6px; color: #3c4a61; font: 0.82rem ui-monospace, SFMono-Regular, Menlo, monospace; padding: 4px 7px; }}
    .quiet {{ color: var(--muted); }}
    details summary {{ cursor: pointer; font-weight: 700; }}
    details p, details ul {{ margin-top: 12px; }}
    .meta {{ color: var(--muted); font-size: 0.8rem; margin-top: 28px; }}
    footer {{ border-top: 1px solid var(--line); color: var(--muted); font-size: 0.85rem; margin-top: 28px; padding-top: 18px; }}
    @media (max-width: 760px) {{
      main {{ padding: 28px 16px 44px; }}
      .intro, .columns {{ display: block; }}
      .decision {{ margin-top: 18px; }}
      .metric-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .lane-grid {{ grid-template-columns: 1fr; }}
      .panel + .panel {{ margin-top: 16px; }}
    }}
  </style>
</head>
<body>
  <main aria-labelledby="page-title">
    <section class="intro">
      <div class="intro-copy">
        <p class="eyebrow">Agent Assurance Harness</p>
        <h1 id="page-title">Portfolio assurance dashboard</h1>
        <p class="subtitle">A metadata-only view of the evidence required before a
        multi-lane assurance result can reach human review.</p>
      </div>
      <div class="decision {decision_class}" aria-label="Portfolio decision">
        <p class="decision-label">Portfolio decision</p>
        <p class="decision-value">{_escape(decision_label)}</p>
      </div>
    </section>

    <section class="metric-grid" aria-label="Portfolio summary">
      {_metric("Lanes", str(len(report.lanes)))}
      {_metric("Passed lanes", str(sum(lane.status == "passed" for lane in report.lanes)))}
      {_metric("Degraded controls", str(sum(lane.degraded_controls for lane in report.lanes)))}
      {_metric("Blocking controls", str(len(report.controls_missed)))}
    </section>

    <section class="panel" aria-labelledby="lanes-heading">
      <h2 id="lanes-heading">Assurance lanes</h2>
      <div class="lane-grid">
        {lane_cards}
      </div>
    </section>

    <section class="columns">
      <div class="panel">
        <h2>Orchestration controls</h2>
        <h3>Controls caught</h3>
        {caught_controls}
        <h3 style="margin-top: 18px">Controls missed</h3>
        {missed_controls}
        <h3 style="margin-top: 18px">Missing lanes</h3>
        {missing_lanes}
        <h3 style="margin-top: 18px">Review-required lanes</h3>
        {review_lanes}
      </div>
      <div class="panel">
        <h2>Negative control</h2>
        <p><span class="status {negative_class}">{negative_status}</span></p>
        <p style="margin-top: 14px"><strong>{_escape(report.negative_control.control_id)}</strong></p>
        <p class="quiet">{_escape(report.negative_control.observed_decision)} because
        <code>{_escape(report.negative_control.reason_code)}</code>.</p>
        <details style="margin-top: 20px">
          <summary>Warnings and limits</summary>
          <ul>{warning_items}</ul>
          <p>{_escape(report.what_it_does_not_show)}</p>
        </details>
      </div>
    </section>

    <p class="meta">Source report: <code>{source_label}</code> · Report SHA-256 prefix:
    <code>{report_hash}</code> · This dashboard contains metadata only.</p>
    <footer>The dashboard presents assurance evidence; it does not replace human review,
    release approval, instructor certification, or production monitoring.</footer>
  </main>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    """Render one explicitly requested local dashboard file."""

    parser = argparse.ArgumentParser(
        description=(
            "Render a metadata-only HTML dashboard from a portfolio assurance JSON report."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        raw = args.input.read_text(encoding="utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("The portfolio report must contain a JSON object.")
        report = DashboardReport.from_dict(value)
        rendered = render_dashboard(
            report,
            source_name=args.input.name,
            report_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "error": "portfolio_dashboard_refused",
                    "message": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(f"dashboard written to {args.output}", file=sys.stderr)
    return 0


def _lane_from_dict(value: object) -> DashboardLane:
    if not isinstance(value, dict):
        raise ValueError("Each portfolio lane must be a JSON object.")
    status = _required_text(value, "status")
    if status not in _LANE_STATUSES:
        raise ValueError(f"Unsupported portfolio lane status: {status!r}.")
    controls_caught = _string_list(value, "controls_caught")
    controls_missed = _string_list(value, "controls_missed")
    degraded_controls = _string_list(value, "degraded_controls_caught")
    reason_code = value.get("reason_code")
    if reason_code is not None and (
        not isinstance(reason_code, str) or not reason_code
    ):
        raise ValueError("Lane reason_code must be a non-empty string or null.")
    return DashboardLane(
        lane_id=_required_text(value, "lane_id"),
        title=_required_text(value, "title"),
        status=status,
        controls_caught=len(controls_caught),
        controls_missed=controls_missed,
        degraded_controls=len(degraded_controls),
        human_gate=_required_text(value, "human_gate"),
        reason_code=reason_code,
    )


def _negative_control_from_dict(
    value: Mapping[str, Any],
) -> DashboardNegativeControl:
    caught = value.get("caught")
    if not isinstance(caught, bool):
        raise ValueError("Negative-control field 'caught' must be boolean.")
    return DashboardNegativeControl(
        control_id=_required_text(value, "control_id"),
        caught=caught,
        observed_decision=_required_text(value, "observed_decision"),
        reason_code=_required_text(value, "reason_code"),
    )


def _required_object(
    value: Mapping[str, Any],
    key: str,
) -> dict[str, Any]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"Portfolio report field {key!r} must be an object.")
    return nested


def _required_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Portfolio report field {key!r} must be a non-empty string.")
    return item


def _string_list(value: Mapping[str, Any], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or not all(
        isinstance(entry, str) and entry for entry in item
    ):
        raise ValueError(f"Portfolio report field {key!r} must be a list of strings.")
    return tuple(item)


def _render_lane(lane: DashboardLane) -> str:
    status_class = _lane_class(lane.status)
    controls_missed = _render_tokens(lane.controls_missed, empty="None")
    reason = (
        f"<p class=\"lane-id\">Reason: <code>{_escape(lane.reason_code)}</code></p>"
        if lane.reason_code
        else ""
    )
    return f"""<article class="lane">
  <div class="lane-header">
    <div>
      <h3>{_escape(lane.title)}</h3>
      <p class="lane-id">{_escape(lane.lane_id)}</p>
      {reason}
    </div>
    <span class="status {status_class}">{_escape(lane.status)}</span>
  </div>
  <div class="lane-stats">
    <span class="lane-stat"><strong>{lane.controls_caught}</strong> caught</span>
    <span class="lane-stat"><strong>{lane.degraded_controls}</strong> degraded</span>
    <span class="lane-stat"><strong>{len(lane.controls_missed)}</strong> missed</span>
  </div>
  <div class="gate"><strong>Human gate:</strong> {_escape(lane.human_gate)}</div>
  <details style="margin-top: 14px">
    <summary>Missed controls</summary>
    {controls_missed}
  </details>
</article>"""


def _metric(label: str, value: str) -> str:
    return f"""<div class="metric">
  <p class="metric-label">{_escape(label)}</p>
  <p class="metric-value">{_escape(value)}</p>
</div>"""


def _render_tokens(values: tuple[str, ...], *, empty: str) -> str:
    if not values:
        return f'<p class="quiet">{_escape(empty)}</p>'
    items = "".join(
        f'<li class="token">{_escape(value)}</li>' for value in values
    )
    return f'<ul class="token-list">{items}</ul>'


def _decision_class(decision: str) -> str:
    if decision == "ready_for_human_review":
        return "decision--pass"
    if decision == "review_required":
        return "decision--review"
    return "decision--blocked"


def _lane_class(status: str) -> str:
    if status == "passed":
        return "status--passed"
    if status == "review_required":
        return "status--review"
    if status == "unavailable":
        return "status--unavailable"
    return "status--blocked"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
