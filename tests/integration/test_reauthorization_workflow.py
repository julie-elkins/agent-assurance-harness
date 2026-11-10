from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
WORKFLOW = REPOSITORY / ".github" / "workflows" / "reauthorization.yml"


def test_reauthorization_workflow_preserves_the_synthetic_evidence_boundary():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Evidence reauthorization contract" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "@main" not in workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert "astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884" in workflow
    assert "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9" in workflow
    assert "uv sync --locked --extra dev" in workflow
    assert "--fail-on-noncompleted" in workflow
    assert "--fail-on-nonreusable" in workflow
    assert "if: ${{ always() }}" in workflow
    assert "retention-days: 14" in workflow
    assert "tools/agent_impact_plan.py" in workflow
    assert "tools/rerun_executor.py" in workflow
    assert "tools/reauthorization_record.py" in workflow
    assert "examples/reauthorization-record/record.json" in workflow
    assert "examples/reauthorization-record/rerun-result.json" in workflow
    assert "release_approval" not in workflow
    assert "github.token" not in workflow

    plan_index = workflow.index("tools/agent_impact_plan.py")
    rerun_index = workflow.index("tools/rerun_executor.py")
    validation_index = workflow.index("tools/reauthorization_record.py")
    upload_index = workflow.index("actions/upload-artifact@")
    assert plan_index < rerun_index < validation_index < upload_index
