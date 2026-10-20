from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
GUIDE = REPOSITORY / "GUIDE.md"
BUILD_GUIDE = REPOSITORY / "BUILD_GUIDE.md"


def test_guide_exists_and_local_references_are_present():
    guide = GUIDE.read_text(encoding="utf-8")

    assert "# Agent Assurance Harness Guide" in guide
    assert "Agent reliability gate" in guide
    assert "verify_assurance_evidence.py" in guide
    assert "How this helps ship production code" in guide
    assert "```mermaid" in guide
    assert "Candidate merge blocked" in guide
    build_guide = BUILD_GUIDE.read_text(encoding="utf-8")
    assert "# Building the Agent Assurance Harness" in build_guide
    assert "How to add a control" in build_guide
    assert "Costs if wrong:" in build_guide

    for relative_path in (
        "README.md",
        "BUILD_GUIDE.md",
        "SECURITY.md",
        "AGENTS.md",
        "src/agent_reliability_lab",
        "examples",
        "tools",
        "tools/render_assurance_summary.py",
        ".github/workflows/reliability.yml",
    ):
        assert (REPOSITORY / relative_path).exists(), relative_path
