"""Bridge the Claude course verifier into the provider-neutral harness.

This adapter imports the public course's checked-in verifier from an explicitly
supplied checkout. It preserves the verifier's evidence tiers and unresolved
states, but exports identifiers and decisions only.

Design rules:

1. The course verifier remains the source of truth for claim extraction and
   citation checking; this module does not maintain a second citation parser.
2. A missing quote is a human-review state, not an automatic stale verdict.
3. Identifier presence is weaker than claim verification and stays labelled.
4. Claim text, quoted source text, raw exceptions, and source bytes never enter
   the adapter report.
5. The local run is bounded by row and unique-page limits.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable, Mapping


CLAUDE_COURSE_ADAPTER_VERSION = 1
DEFAULT_MAX_ROWS = 1_000
DEFAULT_MAX_REQUESTS = 50
_READ_DATE = re.compile(r"\bread\s+(\d{4}-\d{2}-\d{2})\b")


class ClaimVerificationState(str, Enum):
    """The evidence state preserved from the Claude course verifier."""

    GUIDE_REFERENCE_ONLY = "guide_reference_only"
    VERBATIM_VERIFIED = "verbatim_verified"
    VERBATIM_NOT_FOUND = "verbatim_not_found"
    IDENTIFIER_PRESENT_ONLY = "identifier_present_only"
    IDENTIFIER_MISSING = "identifier_missing"
    UNCOVERED = "uncovered"
    UNABLE_TO_CHECK = "unable_to_check"


@dataclass(frozen=True)
class VerifierRow:
    """Safe metadata extracted from one external verifier row."""

    row_id: str
    lesson_id: str
    claim_index: int
    tier: str
    source_url: str | None
    source_reference: str
    source_read_date: str | None
    quote: str | None = None
    identifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaudeClaimLocator:
    """A source location that excludes claim and quote text."""

    lesson_id: str
    claim_index: int
    tier: str
    source_url: str | None
    source_read_date: str | None

    def to_dict(self) -> dict[str, object]:
        """Return the metadata-only locator."""

        return {
            "lesson_id": self.lesson_id,
            "claim_index": self.claim_index,
            "evidence_tier": self.tier,
            "source_url": self.source_url,
            "source_read_date": self.source_read_date,
            "what_it_does_not_show": (
                "This locator identifies a verifier row; it does not reproduce "
                "the claim, quote, or source page."
            ),
        }


@dataclass(frozen=True)
class ClaudeClaimResult:
    """One claim-row outcome with no claim text."""

    row_id: str
    state: ClaimVerificationState
    reason_code: str
    locator: ClaudeClaimLocator

    @property
    def verified(self) -> bool:
        """Return whether the strongest per-claim check passed."""

        return self.state is ClaimVerificationState.VERBATIM_VERIFIED

    def to_dict(self) -> dict[str, object]:
        """Return the safe public representation."""

        return {
            "row_id": self.row_id,
            "state": self.state.value,
            "reason_code": self.reason_code,
            "locator": self.locator.to_dict(),
        }


@dataclass(frozen=True)
class ClaudeCourseVerificationReport:
    """A complete metadata-only report for one Claude course checkout."""

    course_id: str
    course_revision: str | None
    results: tuple[ClaudeClaimResult, ...]
    pages_fetched: int
    max_rows: int
    max_requests: int
    offline: bool
    refusal_code: str | None = None

    @property
    def decision(self) -> str:
        """Return a conservative summary without collapsing evidence states."""

        if self.refusal_code is not None:
            return "blocked"
        return (
            "verified"
            if all(result.verified for result in self.results)
            else "review_required"
        )

    @property
    def passed(self) -> bool:
        """Return true only when every row passed the verbatim check."""

        return self.refusal_code is None and bool(self.results) and all(
            result.verified for result in self.results
        )

    @property
    def counts(self) -> dict[str, int | bool]:
        """Return every state count so incomplete work cannot look clean."""

        counts: dict[str, int | bool] = {
            state.value: sum(result.state is state for result in self.results)
            for state in ClaimVerificationState
        }
        counts["rows_total"] = len(self.results)
        counts["offline"] = self.offline
        counts["counts_reconcile"] = sum(
            value
            for key, value in counts.items()
            if key != "rows_total"
            and key != "offline"
            and key != "counts_reconcile"
            and isinstance(value, int)
        ) == counts["rows_total"]
        return counts

    @property
    def known_findings(self) -> tuple[ClaudeClaimResult, ...]:
        """Return rows with a concrete missing or unavailable check."""

        return tuple(
            result
            for result in self.results
            if result.state
            in {
                ClaimVerificationState.VERBATIM_NOT_FOUND,
                ClaimVerificationState.IDENTIFIER_MISSING,
                ClaimVerificationState.UNABLE_TO_CHECK,
            }
        )

    def to_dict(self) -> dict[str, object]:
        """Return the complete metadata-only report."""

        return {
            "claude_course_adapter_version": CLAUDE_COURSE_ADAPTER_VERSION,
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "decision": self.decision,
            "passed": self.passed,
            "counts": self.counts,
            "pages_fetched": self.pages_fetched,
            "limits": {
                "max_rows": self.max_rows,
                "max_requests": self.max_requests,
            },
            "offline": self.offline,
            "refusal_code": self.refusal_code,
            "results": [result.to_dict() for result in self.results],
            "diagnostics": {
                "warnings": [
                    "The adapter preserves the Claude verifier's evidence tiers; "
                    "identifier presence is not claim verification.",
                    "A missing quote is a human-review signal, not an automatic "
                    "stale-content verdict.",
                ],
                "what_it_does_not_show": (
                    "It does not prove that a lesson teaches the claim correctly "
                    "or that an uncovered claim is false."
                ),
            },
        }

    def to_markdown(self, *, max_findings: int = 20) -> str:
        """Render a compact reviewer summary without claim or quote text."""

        lines = [
            "# Claude Course Verification",
            "",
            f"Decision: `{self.decision.upper()}`",
            "",
            f"- Course: `{self.course_id}`",
            f"- Revision: `{self.course_revision or 'unavailable'}`",
            f"- Pages fetched: `{self.pages_fetched}`",
            f"- Offline: `{self.offline}`",
            f"- Counts: `{_json_counts(self.counts)}`",
        ]
        if self.refusal_code is not None:
            lines.extend(
                [
                    f"- Refusal: `{self.refusal_code}`",
                    "",
                    "The adapter stopped before producing claim results. "
                    "A refusal is not a clean review.",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "A `review_required` result means at least one row was not "
                    "proven by the strongest available check. It is not a claim "
                    "that every unverified row is wrong.",
                ]
            )
        if self.known_findings:
            lines.extend(["", "## Findings with a concrete review signal", ""])
            for result in self.known_findings[:max_findings]:
                locator = result.locator
                lines.extend(
                    [
                        f"- `{locator.lesson_id}` — "
                        f"**{_reason_text(result.reason_code)}**",
                        f"  - Claim row: `{locator.claim_index}`",
                        f"  - Evidence tier: `{locator.tier}`",
                        f"  - Source: `{locator.source_url or 'exam-guide reference'}`",
                    ]
                )
            remaining = len(self.known_findings) - max_findings
            if remaining > 0:
                lines.append(
                    f"- `{remaining}` additional concrete findings are in the JSON report."
                )
        lines.extend(
            [
                "",
                "## Evidence that remains incomplete",
                "",
                "- `guide_reference_only` rows prove the guide reference is the cited "
                "source, not independent claim correctness.",
                "- `identifier_present_only` rows prove a symbol remains on the page, "
                "not that the claim's meaning remains correct.",
                "- `uncovered` rows have no automated evidence tier.",
                "",
                "This report contains identifiers, dates, URLs, states, and counts "
                "only; it does not contain claim or source text.",
                "",
            ]
        )
        return "\n".join(lines)


def adapt_verifier_rows(
    rows: Iterable[VerifierRow],
    *,
    course_id: str,
    course_revision: str | None,
    outcomes: Mapping[str, ClaimVerificationState],
    pages_fetched: int = 0,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    offline: bool = False,
) -> ClaudeCourseVerificationReport:
    """Build a report from typed verifier outcomes for synthetic CI tests."""

    if max_rows <= 0 or max_requests <= 0:
        return _refused_report(
            course_id,
            course_revision,
            max_rows=max_rows,
            max_requests=max_requests,
            offline=offline,
            refusal_code="invalid_limits",
        )
    row_tuple = tuple(rows)
    if len(row_tuple) > max_rows:
        return _refused_report(
            course_id,
            course_revision,
            max_rows=max_rows,
            max_requests=max_requests,
            offline=offline,
            refusal_code="course_row_limit_exceeded",
        )
    results = tuple(
        _result_from_outcome(
            row,
            outcomes.get(row.row_id, ClaimVerificationState.UNABLE_TO_CHECK),
        )
        for row in row_tuple
    )
    return ClaudeCourseVerificationReport(
        course_id=course_id,
        course_revision=course_revision,
        results=results,
        pages_fetched=pages_fetched,
        max_rows=max_rows,
        max_requests=max_requests,
        offline=offline,
    )


def run_claude_course_adapter(
    course_root: Path,
    *,
    course_id: str = "claude-architect-lab",
    offline: bool = False,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    fetcher: Callable[[str], object] | None = None,
) -> ClaudeCourseVerificationReport:
    """Run the checked-in Claude verifier under explicit local limits."""

    root = course_root.resolve()
    if max_rows <= 0 or max_requests <= 0:
        return _refused_report(
            course_id,
            None,
            max_rows=max_rows,
            max_requests=max_requests,
            offline=offline,
            refusal_code="invalid_limits",
        )
    script = root / "scripts" / "verify_claims.py"
    if not root.is_dir():
        return _refused_report(
            course_id,
            None,
            max_rows=max_rows,
            max_requests=max_requests,
            offline=offline,
            refusal_code="course_root_missing",
        )
    if not script.is_file():
        return _refused_report(
            course_id,
            _git_revision(root),
            max_rows=max_rows,
            max_requests=max_requests,
            offline=offline,
            refusal_code="verifier_script_missing",
        )
    try:
        verifier = _load_verifier(script)
        external_rows = tuple(verifier.collect())
    except Exception:
        return _refused_report(
            course_id,
            _git_revision(root),
            max_rows=max_rows,
            max_requests=max_requests,
            offline=offline,
            refusal_code="verifier_load_failed",
        )
    if len(external_rows) > max_rows:
        return _refused_report(
            course_id,
            _git_revision(root),
            max_rows=max_rows,
            max_requests=max_requests,
            offline=offline,
            refusal_code="course_row_limit_exceeded",
        )

    rows = _normalise_rows(external_rows)
    fetch = None
    if not offline:
        fetch_one = fetcher or _default_fetcher()
        fetch = verifier.caching_fetcher(
            fetch_one=_bounded_fetcher(fetch_one, max_requests)
        )
    outcomes: dict[str, ClaimVerificationState] = {}
    for row, external_row in zip(rows, external_rows, strict=True):
        outcomes[row.row_id] = _check_row(
            verifier,
            external_row,
            offline=offline,
            fetch=fetch,
        )
    return adapt_verifier_rows(
        rows,
        course_id=course_id,
        course_revision=_git_revision(root),
        outcomes=outcomes,
        pages_fetched=len(getattr(fetch, "cache", {})) if fetch else 0,
        max_rows=max_rows,
        max_requests=max_requests,
        offline=offline,
    )


def _normalise_rows(external_rows: Iterable[object]) -> tuple[VerifierRow, ...]:
    indexes: dict[str, int] = {}
    rows: list[VerifierRow] = []
    for external_row in external_rows:
        lesson_id = str(external_row.lesson)
        claim_index = indexes.get(lesson_id, 0) + 1
        indexes[lesson_id] = claim_index
        row_id = f"{lesson_id}:claim-{claim_index}"
        source = str(external_row.source)
        rows.append(
            VerifierRow(
                row_id=row_id,
                lesson_id=lesson_id,
                claim_index=claim_index,
                tier=str(external_row.tier),
                source_url=external_row.url,
                source_reference=source,
                source_read_date=_read_date(source),
                quote=external_row.quote,
                identifiers=tuple(external_row.symbols),
            )
        )
    return tuple(rows)


def _check_row(
    verifier: ModuleType,
    external_row: object,
    *,
    offline: bool,
    fetch: object,
) -> ClaimVerificationState:
    tier = str(external_row.tier)
    if tier == "GUIDE":
        return ClaimVerificationState.GUIDE_REFERENCE_ONLY
    if tier == "UNCOVERED":
        return ClaimVerificationState.UNCOVERED
    if offline or fetch is None:
        return ClaimVerificationState.UNABLE_TO_CHECK
    if tier == "VERBATIM":
        try:
            result = verifier.check_quote(
                external_row.url,
                external_row.quote,
                fetch=fetch,
            )
        except Exception:
            return ClaimVerificationState.UNABLE_TO_CHECK
        return (
            ClaimVerificationState.VERBATIM_VERIFIED
            if result.found
            else ClaimVerificationState.VERBATIM_NOT_FOUND
        )
    if tier == "IDENTIFIER":
        try:
            missing = [
                symbol
                for symbol in external_row.symbols
                if not verifier.check_quote(
                    external_row.url,
                    symbol,
                    fetch=fetch,
                ).found
            ]
        except Exception:
            return ClaimVerificationState.UNABLE_TO_CHECK
        return (
            ClaimVerificationState.IDENTIFIER_MISSING
            if missing
            else ClaimVerificationState.IDENTIFIER_PRESENT_ONLY
        )
    return ClaimVerificationState.UNABLE_TO_CHECK


def _result_from_outcome(
    row: VerifierRow,
    state: ClaimVerificationState,
) -> ClaudeClaimResult:
    reasons = {
        ClaimVerificationState.GUIDE_REFERENCE_ONLY: "guide_reference_only",
        ClaimVerificationState.VERBATIM_VERIFIED: "verbatim_verified",
        ClaimVerificationState.VERBATIM_NOT_FOUND: "verbatim_not_found",
        ClaimVerificationState.IDENTIFIER_PRESENT_ONLY: "identifier_presence_only",
        ClaimVerificationState.IDENTIFIER_MISSING: "identifier_missing",
        ClaimVerificationState.UNCOVERED: "no_automated_evidence",
        ClaimVerificationState.UNABLE_TO_CHECK: "evidence_unavailable",
    }
    return ClaudeClaimResult(
        row_id=row.row_id,
        state=state,
        reason_code=reasons[state],
        locator=ClaudeClaimLocator(
            lesson_id=row.lesson_id,
            claim_index=row.claim_index,
            tier=row.tier,
            source_url=row.source_url,
            source_read_date=row.source_read_date,
        ),
    )


def _load_verifier(path: Path) -> ModuleType:
    module_name = f"_claude_course_verifier_{hashlib.sha256(str(path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("verifier module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _default_fetcher() -> Callable[[str], object]:
    from course_doctor.citations import _fetch

    return _fetch


def _bounded_fetcher(
    fetcher: Callable[[str], object],
    max_requests: int,
) -> Callable[[str], object]:
    seen: set[str] = set()

    def fetch(url: str) -> object:
        if url not in seen:
            if len(seen) >= max_requests:
                raise RuntimeError("request_limit_exceeded")
            seen.add(url)
        return fetcher(url)

    return fetch


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else None


def _read_date(source_reference: str) -> str | None:
    match = _READ_DATE.search(source_reference)
    return match.group(1) if match else None


def _refused_report(
    course_id: str,
    course_revision: str | None,
    *,
    max_rows: int,
    max_requests: int,
    offline: bool,
    refusal_code: str,
) -> ClaudeCourseVerificationReport:
    return ClaudeCourseVerificationReport(
        course_id=course_id,
        course_revision=course_revision,
        results=(),
        pages_fetched=0,
        max_rows=max_rows,
        max_requests=max_requests,
        offline=offline,
        refusal_code=refusal_code,
    )


def _reason_text(reason_code: str) -> str:
    return {
        "verbatim_not_found": (
            "Exact documentation wording was not found; human review is required."
        ),
        "identifier_missing": (
            "A documented identifier was not found; check for rename or removal."
        ),
        "evidence_unavailable": (
            "The source could not be checked; this is not a pass."
        ),
    }.get(reason_code, reason_code.replace("_", " "))


def _json_counts(counts: Mapping[str, object]) -> str:
    import json

    return json.dumps(counts, sort_keys=True)
