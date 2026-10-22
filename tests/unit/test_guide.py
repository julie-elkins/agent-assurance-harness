from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
GUIDE = REPOSITORY / "GUIDE.md"
BUILD_GUIDE = REPOSITORY / "BUILD_GUIDE.md"
DELIVERY_STANDARD = REPOSITORY / "PRODUCTION_DELIVERY_STANDARD.md"
ASSURANCE_SKILL = REPOSITORY / "skills" / "agent-assurance-harness" / "SKILL.md"
SHOWCASE = REPOSITORY / "SHOWCASE.md"
ROLE_GUIDE = REPOSITORY / "ROLE_ALIGNMENT_GUIDE.md"


def test_guide_exists_and_local_references_are_present():
    guide = GUIDE.read_text(encoding="utf-8")

    assert "# Agent Assurance Harness Guide" in guide
    assert "Agent reliability gate" in guide
    assert "verify_assurance_evidence.py" in guide
    assert "How this helps ship production code" in guide
    assert "launch-to-field" in guide
    assert "Instructor calibration" in guide
    assert "```mermaid" in guide
    assert "Candidate merge blocked" in guide
    build_guide = BUILD_GUIDE.read_text(encoding="utf-8")
    assert "# Building the Agent Assurance Harness" in build_guide
    assert "How to add a control" in build_guide
    assert "Costs if wrong:" in build_guide
    skill = ASSURANCE_SKILL.read_text(encoding="utf-8")
    assert "name: agent-assurance-harness" in skill
    assert "pinned-action content-parity" in skill
    standard = DELIVERY_STANDARD.read_text(encoding="utf-8")
    assert "# Production Delivery Standard" in standard
    assert "The ten controls" in standard
    showcase = SHOWCASE.read_text(encoding="utf-8")
    assert "tools/claude_course_adapter.py" in showcase
    assert "REVIEW_REQUIRED" in showcase
    assert "rows_total" in showcase
    role_guide = ROLE_GUIDE.read_text(encoding="utf-8")
    assert "Requirement-to-evidence map" in role_guide
    assert "tools/launch_to_field_report.py" in role_guide
    assert "tools/instructor_calibration_report.py" in role_guide
    assert "tools/portfolio_assurance_report.py" in role_guide
    assert "--course-root" in role_guide
    assert "Instructor calibration" in showcase
    assert "Combined portfolio assurance report" in showcase
    assert "Add the public Claude course locally" in showcase
    assert "public_course_review_packet.py" in showcase
    assert "public_course_review_adjudication.py" in showcase

    for relative_path in (
        "README.md",
        "BUILD_GUIDE.md",
        "SECURITY.md",
        "AGENTS.md",
        "src/agent_reliability_lab",
        "examples",
        "tools",
        "tools/render_assurance_summary.py",
        "tools/golden_trace_report.py",
        "SHOWCASE.md",
        "ROLE_ALIGNMENT_GUIDE.md",
        "examples/traces/golden-manifest.json",
        ".github/workflows/reliability.yml",
        "skills/agent-assurance-harness/SKILL.md",
    ):
        assert (REPOSITORY / relative_path).exists(), relative_path
