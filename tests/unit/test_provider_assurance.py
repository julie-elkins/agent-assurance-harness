from agent_reliability_lab.provider_assurance import run_provider_assurance


def test_provider_assurance_passes_both_shapes_and_catches_budget_control():
    report = run_provider_assurance()

    assert report.passed is True
    assert [item.provider_id for item in report.providers] == [
        "anthropic",
        "openai",
    ]
    assert all(item.credential_value_observed is False for item in report.providers)
    assert all(item.live_enabled is False for item in report.providers)
    assert all(item.budgets_within_limits for item in report.providers)
    assert report.negative_control.caught is True
    assert report.negative_control.refusal_count == 9
    assert report.negative_control.over_budget_scenario_count == 9


def test_provider_assurance_report_is_metadata_only():
    report = run_provider_assurance()
    serialized = str(report.to_dict())

    assert "'prompt':" not in serialized
    assert "provider output" not in serialized
    assert "credential_value" in serialized
