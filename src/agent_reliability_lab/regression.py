"""Comparison of identifier-only replay evaluations for harness regressions.

Design rules:

1. Compare evaluated findings by scenario and check, never raw traces or provider text.
2. Require both replays and both harness manifests before reporting a comparison result.
3. Block safety and evidence regressions; report task-outcome regressions separately.
4. Preserve structured refusals when a comparison cannot establish a result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import AssuranceDimension, Finding, FindingStatus
from .replay import (
    HarnessChangeManifest,
    ReplayFile,
    ReplayRefusal,
    load_replay_file,
    run_replay,
)


_BLOCKING_DIMENSIONS = frozenset(
    {
        AssuranceDimension.EVIDENCE_COMPLETENESS,
        AssuranceDimension.ABSTENTION,
        AssuranceDimension.SIDE_EFFECT_AUTHORIZATION,
        AssuranceDimension.EVALUATOR_VALIDITY,
    }
)


@dataclass(frozen=True)
class RegressionFinding:
    """One candidate degradation relative to the approved baseline."""

    scenario_id: str
    check_id: str
    category: str
    message: str
    dimension: AssuranceDimension
    blocking: bool
    changed_components: tuple[str, ...]
    baseline_status: FindingStatus
    candidate_status: FindingStatus
    baseline_evidence: tuple[str, ...]
    candidate_evidence: tuple[str, ...]
    newly_missing_evidence: tuple[str, ...]
    does_not_show: str

    def to_dict(self) -> dict[str, object]:
        """Return an identifier-only regression finding."""

        return {
            "scenario_id": self.scenario_id,
            "check_id": self.check_id,
            "category": self.category,
            "dimension": self.dimension.value,
            "blocking": self.blocking,
            "changed_components": list(self.changed_components),
            "message": self.message,
            "baseline_status": self.baseline_status.value,
            "candidate_status": self.candidate_status.value,
            "baseline_evidence": list(self.baseline_evidence),
            "candidate_evidence": list(self.candidate_evidence),
            "newly_missing_evidence": list(self.newly_missing_evidence),
            "what_it_does_not_show": self.does_not_show,
        }


@dataclass(frozen=True)
class RegressionReport:
    """The result of comparing one candidate replay with one baseline replay."""

    baseline_source: str
    candidate_source: str
    expected_scenario_count: int
    baseline_change: HarnessChangeManifest | None = None
    candidate_change: HarnessChangeManifest | None = None
    findings: tuple[RegressionFinding, ...] = ()
    refusal: ReplayRefusal | None = None

    @property
    def failed(self) -> bool:
        """Return whether the candidate must fail a release gate."""

        return self.refusal is not None or any(
            finding.blocking for finding in self.findings
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe report without raw trace content."""

        return {
            "baseline_source": self.baseline_source,
            "candidate_source": self.candidate_source,
            "expected_scenario_count": self.expected_scenario_count,
            "baseline_harness_change": (
                self.baseline_change.to_dict()
                if self.baseline_change is not None
                else None
            ),
            "candidate_harness_change": (
                self.candidate_change.to_dict()
                if self.candidate_change is not None
                else None
            ),
            "passed": not self.failed,
            "findings": [finding.to_dict() for finding in self.findings],
            "refusal": (
                self.refusal.to_dict() if self.refusal is not None else None
            ),
            "diagnostics": {
                "warnings": [
                    "Regression compares evaluator findings from identifier-only replays; it does not establish causality.",
                    "Blocking is reserved for safety and evidence dimensions; task-outcome changes remain visible as non-blocking observations.",
                ],
                "what_it_does_not_show": (
                    "It does not show which prompt, model, tool, or policy change caused "
                    "a regression, and it does not measure live-provider behaviour."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Return a reviewable regression summary."""

        if self.refusal is not None:
            return (
                "# Harness Regression\n\n"
                f"**REFUSED** `{self.refusal.error}`: {self.refusal.message}\n\n"
                f"Guidance: {self.refusal.guidance}"
            )
        assert self.baseline_change is not None
        assert self.candidate_change is not None
        outcome = "PASS" if not self.failed else "BLOCKED"
        lines = [
            "# Harness Regression",
            "",
            f"Baseline: `{self.baseline_source}`",
            f"Candidate: `{self.candidate_source}`",
            f"Baseline change: `{self.baseline_change.change_id}`",
            f"Candidate change: `{self.candidate_change.change_id}`",
            "Changed components: "
            + ", ".join(
                f"`{component}`"
                for component in self.candidate_change.components
            ),
            f"Scenarios checked: {self.expected_scenario_count}",
            f"Overall result: **{outcome}**",
            "",
        ]
        if not self.findings:
            lines.append("No candidate degradation was observed.")
        else:
            lines.extend(["## Findings", ""])
            for finding in self.findings:
                gate = "BLOCKING" if finding.blocking else "OBSERVATION"
                lines.append(
                    f"- **{gate}** `{finding.category}` "
                    f"`{finding.scenario_id}`/`{finding.check_id}`: "
                    f"{finding.message}"
                )
        return "\n".join(lines)


def compare_replay_files(
    baseline_path: Path,
    candidate_path: Path,
) -> RegressionReport:
    """Load and compare two local replay files."""

    baseline = load_replay_file(baseline_path)
    if baseline.refusal is not None:
        return _input_refusal(
            baseline_source=str(baseline_path),
            candidate_source=str(candidate_path),
            refusal=baseline.refusal,
            role="baseline",
        )
    candidate = load_replay_file(candidate_path)
    if candidate.refusal is not None:
        return _input_refusal(
            baseline_source=str(baseline_path),
            candidate_source=str(candidate_path),
            refusal=candidate.refusal,
            role="candidate",
        )
    assert baseline.replay is not None
    assert candidate.replay is not None
    return compare_replays(
        baseline.replay,
        candidate.replay,
        baseline_source=str(baseline_path),
        candidate_source=str(candidate_path),
    )


def compare_replays(
    baseline: ReplayFile,
    candidate: ReplayFile,
    *,
    baseline_source: str = "baseline",
    candidate_source: str = "candidate",
) -> RegressionReport:
    """Compare two already-normalized replay files."""

    if baseline.agent_id != candidate.agent_id:
        return _comparison_refusal(
            baseline_source,
            candidate_source,
            error="agent_id_mismatch",
            message="Baseline and candidate replays identify different agents.",
            guidance="Compare two runs from the same agent integration.",
        )
    if baseline.harness_change is None:
        return _manifest_refusal(
            baseline_source,
            candidate_source,
            role="baseline",
        )
    if candidate.harness_change is None:
        return _manifest_refusal(
            baseline_source,
            candidate_source,
            role="candidate",
        )
    baseline_report = run_replay(baseline, source=baseline_source)
    if baseline_report.refusal is not None:
        return _evaluation_refusal(
            baseline_source,
            candidate_source,
            baseline_report.refusal,
            role="baseline",
        )
    candidate_report = run_replay(candidate, source=candidate_source)
    if candidate_report.refusal is not None:
        return _evaluation_refusal(
            baseline_source,
            candidate_source,
            candidate_report.refusal,
            role="candidate",
        )
    assert baseline_report.agent_report is not None
    assert candidate_report.agent_report is not None
    baseline_findings = _findings_by_scenario(baseline, baseline_report)
    candidate_findings = _findings_by_scenario(candidate, candidate_report)
    if set(baseline_findings) != set(candidate_findings):
        return _comparison_refusal(
            baseline_source,
            candidate_source,
            error="scenario_alignment_failed",
            message="Baseline and candidate findings could not be aligned by scenario ID.",
            guidance="Compare complete replay files covering the same scenario set.",
        )

    findings = []
    for scenario_id in sorted(baseline_findings):
        regression = _compare_finding(
            scenario_id,
            baseline_findings[scenario_id],
            candidate_findings[scenario_id],
            changed_components=candidate.harness_change.components,
        )
        if regression is not None:
            findings.append(regression)
    return RegressionReport(
        baseline_source=baseline_source,
        candidate_source=candidate_source,
        expected_scenario_count=baseline_report.expected_scenario_count,
        baseline_change=baseline.harness_change,
        candidate_change=candidate.harness_change,
        findings=tuple(findings),
    )


def _compare_finding(
    scenario_id: str,
    baseline: Finding,
    candidate: Finding,
    *,
    changed_components: tuple[str, ...],
) -> RegressionFinding | None:
    baseline_bad = baseline.status in {
        FindingStatus.FAILED,
        FindingStatus.REFUSED,
    }
    candidate_bad = candidate.status in {
        FindingStatus.FAILED,
        FindingStatus.REFUSED,
    }
    newly_missing = tuple(
        evidence
        for evidence in candidate.missing_evidence
        if evidence not in baseline.missing_evidence
    )
    if newly_missing and candidate.dimension in _BLOCKING_DIMENSIONS:
        category = "evidence_loss"
        message = (
            f"{candidate.check_id} lost required evidence: "
            + ", ".join(newly_missing)
            + "."
        )
    elif candidate_bad and not baseline_bad:
        category = (
            "new_refusal"
            if candidate.status is FindingStatus.REFUSED
            else "new_failure"
        )
        message = (
            f"{candidate.check_id} changed from {baseline.status.value} to "
            f"{candidate.status.value}: {candidate.message}"
        )
    elif baseline.status is FindingStatus.COMPLETED and (
        candidate.status is not FindingStatus.COMPLETED
    ):
        category = "status_regression"
        message = (
            f"{candidate.check_id} changed from completed to "
            f"{candidate.status.value}."
        )
    elif newly_missing:
        category = "evidence_loss"
        message = (
            f"{candidate.check_id} lost required evidence: "
            + ", ".join(newly_missing)
            + "."
        )
    else:
        return None
    return RegressionFinding(
        scenario_id=scenario_id,
        check_id=candidate.check_id,
        category=category,
        message=message,
        dimension=candidate.dimension,
        blocking=(
            category == "evidence_loss"
            or candidate.dimension in _BLOCKING_DIMENSIONS
        ),
        changed_components=changed_components,
        baseline_status=baseline.status,
        candidate_status=candidate.status,
        baseline_evidence=baseline.evidence,
        candidate_evidence=candidate.evidence,
        newly_missing_evidence=newly_missing,
        does_not_show=(
            "It does not show which upstream harness change caused the observed regression."
        ),
    )


def _findings_by_scenario(replay: ReplayFile, report) -> dict[str, Finding]:
    assert report.agent_report is not None
    if len(replay.cases) != len(report.agent_report.findings):
        raise RuntimeError("Replay cases and evaluator findings are out of sync.")
    return {
        case.scenario_id: finding
        for case, finding in zip(
            replay.cases,
            report.agent_report.findings,
            strict=True,
        )
    }


def _comparison_refusal(
    baseline_source: str,
    candidate_source: str,
    *,
    error: str,
    message: str,
    guidance: str,
) -> RegressionReport:
    return RegressionReport(
        baseline_source=baseline_source,
        candidate_source=candidate_source,
        expected_scenario_count=0,
        refusal=ReplayRefusal(
            error=error,
            message=message,
            guidance=guidance,
            source=candidate_source,
        ),
    )


def _manifest_refusal(
    baseline_source: str,
    candidate_source: str,
    *,
    role: str,
) -> RegressionReport:
    return _comparison_refusal(
        baseline_source,
        candidate_source,
        error="harness_change_manifest_required",
        message=f"The {role} replay has no harness_change manifest.",
        guidance=(
            "Add identifier-only change_id and non-empty components before comparing "
            "harness runs."
        ),
    )


def _input_refusal(
    *,
    baseline_source: str,
    candidate_source: str,
    refusal: ReplayRefusal,
    role: str,
) -> RegressionReport:
    return RegressionReport(
        baseline_source=baseline_source,
        candidate_source=candidate_source,
        expected_scenario_count=0,
        refusal=ReplayRefusal(
            error="comparison_input_refused",
            message=f"The {role} replay could not be loaded: {refusal.message}",
            guidance=refusal.guidance,
            source=refusal.source,
        ),
    )


def _evaluation_refusal(
    baseline_source: str,
    candidate_source: str,
    refusal: ReplayRefusal,
    *,
    role: str,
) -> RegressionReport:
    return RegressionReport(
        baseline_source=baseline_source,
        candidate_source=candidate_source,
        expected_scenario_count=0,
        refusal=ReplayRefusal(
            error="comparison_evaluation_refused",
            message=f"The {role} replay could not be evaluated: {refusal.message}",
            guidance=refusal.guidance,
            source=refusal.source,
        ),
    )
