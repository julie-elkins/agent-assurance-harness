"""Contract tests for the synthetic production AI engineering bridge lab."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "examples/production-ai-engineering-bridge-lab/run_lab.py"


def test_production_bridge_lab_is_deterministic_and_bounded() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    result = json.loads(completed.stdout)

    assert result["contract_status"] == "pass"
    assert result["offline"] is True
    assert result["metadata_only"] is True
    assert result["transport_status"] == "ok"
    assert result["semantic_outcome"] == "empty_context"
    assert result["guardrail_coverage"] == "complete_for_synthetic_boundaries"
    assert result["privacy"] == "identifier_only"
    assert result["operating_targets"] == "within_synthetic_targets"
    assert result["retry_count"] == 0
    assert result["estimated_cost_usd"] == 0.0
    assert result["latency_ms"] == 120
    assert result["incident_response"]["external_action"] == (
        "blocked_pending_approval"
    )
    assert result["incident_response"]["evidence_preserved"] is True
    assert "live model quality" in result["what_it_does_not_prove"]
