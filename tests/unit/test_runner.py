from agent_reliability_lab.runner import failed_checks, run_comparison


def test_comparison_keeps_baseline_failure_visible():
    report = run_comparison()

    assert report.scenario_count == 10
    assert len(report.contracts) == 10
    assert [item.agent_id for item in report.reports] == ["naive", "guarded"]
    assert report.reports[0].passed is False
    assert report.reports[1].passed is True
    assert failed_checks(report) == 10


def test_each_guarded_scenario_has_evidence():
    report = run_comparison()
    guarded = report.reports[1]

    assert all(finding.evidence for finding in guarded.findings)
    assert all(finding.required_evidence for finding in guarded.findings)
    assert all(finding.does_not_show for finding in guarded.findings)


def test_mutation_option_reports_evaluator_checks():
    report = run_comparison(include_mutations=True)

    assert len(report.mutation_tests) == 3
    assert all(mutation.applied for mutation in report.mutation_tests)
    assert all(mutation.caught for mutation in report.mutation_tests)


def test_markdown_summary_keeps_dimensions_separate():
    summary = run_comparison().to_markdown()

    assert "## Assurance dimensions" in summary
    assert "`evidence_completeness`" in summary
    assert "## Evaluator validity" in summary


def test_provider_budget_summary_is_visible_in_markdown():
    from agent_reliability_lab.providers import mock_provider_adapters
    from agent_reliability_lab.runner import run_adapters_comparison

    summary = run_adapters_comparison(
        mock_provider_adapters("openai"),
    ).to_markdown()

    assert "## Efficiency and budget" in summary
    assert "Output tokens" in summary
    assert "Estimated cost (USD)" in summary
    assert "Within limits" in summary
