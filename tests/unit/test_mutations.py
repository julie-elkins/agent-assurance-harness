from agent_reliability_lab.mutations import all_mutations_caught, run_mutation_tests


def test_controlled_evidence_mutations_are_applied_and_caught():
    results = run_mutation_tests()

    assert all_mutations_caught(results)
    assert all(result.finding.missing_evidence for result in results)
