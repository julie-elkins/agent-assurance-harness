from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
GUIDE = REPOSITORY / "GUIDE.md"


def test_guide_exists_and_local_references_are_present():
    guide = GUIDE.read_text(encoding="utf-8")

    assert "# Agent Assurance Harness Guide" in guide
    assert "Agent reliability gate" in guide
    assert "verify_assurance_evidence.py" in guide
    assert "How this helps ship production code" in guide
    assert "```mermaid" in guide
    assert "Candidate merge blocked" in guide

    for relative_path in (
        "README.md",
        "SECURITY.md",
        "AGENTS.md",
        "src/agent_reliability_lab",
        "examples",
        "tools",
        ".github/workflows/reliability.yml",
    ):
        assert (REPOSITORY / relative_path).exists(), relative_path
