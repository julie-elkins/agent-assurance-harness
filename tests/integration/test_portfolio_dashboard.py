import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
PORTFOLIO_TOOL = ROOT / "tools" / "portfolio_assurance_report.py"
DASHBOARD_TOOL = ROOT / "tools" / "portfolio_dashboard.py"
_SPEC = importlib.util.spec_from_file_location(
    "portfolio_dashboard",
    DASHBOARD_TOOL,
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
DashboardReport = _MODULE.DashboardReport
render_dashboard = _MODULE.render_dashboard


def test_dashboard_renders_metadata_only_portfolio_report(tmp_path):
    report_path = tmp_path / "portfolio.json"
    dashboard_path = tmp_path / "dashboard.html"
    subprocess.run(
        [
            sys.executable,
            str(PORTFOLIO_TOOL),
            "--workspace",
            str(tmp_path / "workspace"),
            "--output",
            str(report_path),
            "--fail-on-findings",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            str(DASHBOARD_TOOL),
            "--input",
            str(report_path),
            "--output",
            str(dashboard_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    html = dashboard_path.read_text(encoding="utf-8")
    assert "Portfolio assurance dashboard" in html
    assert "ready for human review" in html
    assert "agent_assurance" in html
    assert "course_doctor" in html
    assert "source_bytes" not in html
    assert "provider_output" not in html
    assert "DashboardReport" not in result.stderr


def test_dashboard_escapes_metadata_values():
    report = DashboardReport.from_dict(
        {
            "decision": "blocked",
            "passed": False,
            "lanes": [
                {
                    "lane_id": "lane-<unsafe>",
                    "title": "<script>alert(1)</script>",
                    "status": "blocked",
                    "controls_caught": [],
                    "controls_missed": ["missing-check"],
                    "degraded_controls_caught": [],
                    "human_gate": "Human review <required>",
                    "reason_code": "worker_unavailable",
                }
            ],
            "controls_caught": [],
            "controls_missed": ["missing-check"],
            "missing_lanes": ["lane-<unsafe>"],
            "review_required_lanes": [],
            "negative_control": {
                "control_id": "control-1",
                "caught": True,
                "observed_decision": "blocked",
                "reason_code": "missing_lane",
            },
            "diagnostics": {
                "warnings": ["<warning>"],
                "what_it_does_not_show": "<limit>",
            },
        }
    )

    rendered = render_dashboard(
        report,
        source_name="portfolio.json",
        report_sha256="a" * 64,
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "&lt;warning&gt;" in rendered
    assert "&lt;limit&gt;" in rendered


def test_dashboard_refuses_incomplete_report(tmp_path):
    input_path = tmp_path / "incomplete.json"
    output_path = tmp_path / "dashboard.html"
    input_path.write_text(json.dumps({"decision": "ready_for_human_review"}))

    result = subprocess.run(
        [
            sys.executable,
            str(DASHBOARD_TOOL),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "portfolio_dashboard_refused" in result.stderr
    assert not output_path.exists()
