from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
README = REPOSITORY / "README.md"
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
    assert "Bounded synthetic agent-memory policy" in guide
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
    assert "tools/agent_memory_policy_report.py" in role_guide
    assert "DESIGN_DECISIONS.md" in README.read_text(encoding="utf-8")
    assert "tools/portfolio_assurance_report.py" in role_guide
    assert "--course-root" in role_guide
    assert "Instructor calibration" in showcase
    assert "Combined portfolio assurance report" in showcase
    assert "Add the public Claude course locally" in showcase
    assert "public_course_review_packet.py" in showcase
    assert "public_course_review_adjudication.py" in showcase
    assert "public_course_change_plan.py" in showcase
    assert "public_course_post_change.py" in showcase
    assert "tools/developer_workflow_report.py" in showcase
    assert "Green-but-unaudited negative control caught" in showcase
    assert "DEVELOPER_WORKFLOW_ASSURANCE.md" in showcase
    assert "tools/developer_workflow_report.py" in README.read_text(encoding="utf-8")
    assert "Security hardening" in README.read_text(encoding="utf-8")
    assert "Security hardening around the harness" in guide
    assert "phases 43–47" in build_guide
    assert "immutable commit" in skill
    assert "supply-chain hardening" in role_guide.lower()

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
        ".github/workflows/dependency-review.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/scorecard.yml",
        ".github/dependabot.yml",
        ".github/CODEOWNERS",
        "skills/agent-assurance-harness/SKILL.md",
    ):
        assert (REPOSITORY / relative_path).exists(), relative_path
