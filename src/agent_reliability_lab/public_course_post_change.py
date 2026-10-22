"""Verify a planned public-course change against a later safe verifier report.

Design rules:

1. The post-change report must identify the same course and a different
   revision from the change plan.
2. Every planned target must be present in the later report and reach the
   state expected for its evidence tier.
3. New blocking findings are independent regressions and block the result.
4. The report contains metadata only; it never carries course text, source
   quotations, or a content diff.
5. A verified targeted scope still requires human approval before publication.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from .claude_course_adapter import (
    CLAUDE_COURSE_ADAPTER_VERSION,
    ClaimVerificationState,
)
from .public_course_change_plan import PUBLIC_COURSE_CHANGE_PLAN_VERSION
from .public_course_review import HumanDisposition


PUBLIC_COURSE_POST_CHANGE_VERSION = 1
_ADAPTER_VERSION = CLAUDE_COURSE_ADAPTER_VERSION
_BLOCKING_STATES = frozenset(
    {
        ClaimVerificationState.IDENTIFIER_MISSING.value,
        ClaimVerificationState.UNABLE_TO_CHECK.value,
    }
)
_RECOVERY_STATES = {
    ClaimVerificationState.VERBATIM_NOT_FOUND.value: frozenset(
        {ClaimVerificationState.VERBATIM_VERIFIED.value}
    ),
    ClaimVerificationState.IDENTIFIER_MISSING.value: frozenset(
        {
            ClaimVerificationState.IDENTIFIER_PRESENT_ONLY.value,
            ClaimVerificationState.VERBATIM_VERIFIED.value,
        }
    ),
    ClaimVerificationState.UNABLE_TO_CHECK.value: frozenset(
        {
            ClaimVerificationState.IDENTIFIER_PRESENT_ONLY.value,
            ClaimVerificationState.VERBATIM_VERIFIED.value,
        }
    ),
}


@dataclass(frozen=True)
class TargetVerification:
    """The safe before/after result for one planned finding."""

    finding_id: str
    lesson_id: str
    claim_index: int
    disposition: HumanDisposition
    before_state: str
    after_state: str | None
    outcome: str
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only target result."""

        return {
            "finding_id": self.finding_id,
            "lesson_id": self.lesson_id,
            "claim_index": self.claim_index,
            "disposition": self.disposition.value,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "what_it_does_not_show": (
                "This result does not reproduce course text or source quotations."
            ),
        }


@dataclass(frozen=True)
class PublicCoursePostChangeVerification:
    """The bounded result of checking a planned change against new evidence."""

    course_id: str
    before_revision: str | None
    after_revision: str | None
    plan_digest: str | None
    after_decision: str
    after_counts: dict[str, int | bool]
    targets: tuple[TargetVerification, ...]
    new_blocking_findings: tuple[str, ...]
    refusal_code: str | None = None
    human_approval_required: bool = True

    @property
    def decision(self) -> str:
        """Return the conservative post-change handoff state."""

        if self.refusal_code is not None:
            return "blocked"
        return "verified_targeted_scope"

    @property
    def passed(self) -> bool:
        """Return whether all planned controls passed."""

        return self.refusal_code is None

    @property
    def next_action(self) -> str:
        """Return the next bounded human action."""

        if self.refusal_code is not None:
            return "correct_post_change_verification_input"
        return "human_approval_required_before_publication"

    @property
    def verification_digest(self) -> str:
        """Return a stable fingerprint of the safe verification result."""

        payload = {
            "public_course_post_change_version": (
                PUBLIC_COURSE_POST_CHANGE_VERSION
            ),
            "course_id": self.course_id,
            "before_revision": self.before_revision,
            "after_revision": self.after_revision,
            "plan_digest": self.plan_digest,
            "after_decision": self.after_decision,
            "after_counts": self.after_counts,
            "targets": [target.to_dict() for target in self.targets],
            "new_blocking_findings": list(self.new_blocking_findings),
            "refusal_code": self.refusal_code,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_dict(self) -> dict[str, object]:
        """Return the complete metadata-only verification result."""

        return {
            "public_course_post_change_version": (
                PUBLIC_COURSE_POST_CHANGE_VERSION
            ),
            "course_id": self.course_id,
            "before_revision": self.before_revision,
            "after_revision": self.after_revision,
            "plan_digest": self.plan_digest,
            "verification_digest": self.verification_digest,
            "after_decision": self.after_decision,
            "after_counts": self.after_counts,
            "decision": self.decision,
            "passed": self.passed,
            "next_action": self.next_action,
            "targets": [target.to_dict() for target in self.targets],
            "new_blocking_findings": list(self.new_blocking_findings),
            "refusal_code": self.refusal_code,
            "human_approval_required": self.human_approval_required,
            "diagnostics": {
                "warnings": [
                    "This report compares safe metadata from two bounded review states.",
                    "A targeted verification pass does not approve publication.",
                ],
                "what_it_does_not_show": (
                    "It does not prove course correctness, learner outcomes, or "
                    "the quality of the human content change."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing post-change summary."""

        lines = [
            "# Public Course Post-Change Verification",
            "",
            f"Decision: `{self.decision}`",
            "",
            f"- Course: `{self.course_id}`",
            f"- Before revision: `{self.before_revision or 'unavailable'}`",
            f"- After revision: `{self.after_revision or 'unavailable'}`",
            f"- After evidence decision: `{self.after_decision}`",
            f"- New blocking findings: `{len(self.new_blocking_findings)}`",
            f"- Next action: `{self.next_action}`",
        ]
        if self.refusal_code is not None:
            lines.append(f"- Refusal: `{self.refusal_code}`")
        lines.extend(
            [
                "",
                "| Lesson | Claim | Before | After | Outcome |",
                "| --- | ---: | --- | --- | --- |",
            ]
        )
        for target in self.targets:
            lines.append(
                f"| `{target.lesson_id}` | `{target.claim_index}` | "
                f"`{target.before_state}` | `{target.after_state or 'unavailable'}` | "
                f"`{target.outcome}` |"
            )
        lines.extend(
            [
                "",
                "A verified targeted scope still requires human approval before publication.",
                "",
            ]
        )
        return "\n".join(lines)


def build_public_course_post_change_verification(
    change_plan: Mapping[str, object],
    post_report: Mapping[str, object],
) -> PublicCoursePostChangeVerification:
    """Compare a change plan with a later safe adapter report."""

    course_id = _safe_text(change_plan.get("course_id")) or "unavailable"
    before_revision = _optional_text(change_plan.get("course_revision"))
    after_revision = _optional_text(post_report.get("course_revision"))
    plan_digest = _optional_text(change_plan.get("plan_digest"))
    after_decision = _safe_text(post_report.get("decision")) or "unavailable"
    after_counts = _counts(post_report.get("counts"))

    refusal = _validate_inputs(
        change_plan=change_plan,
        post_report=post_report,
        course_id=course_id,
        before_revision=before_revision,
        after_revision=after_revision,
        plan_digest=plan_digest,
    )
    if refusal is not None:
        return _blocked_verification(
            course_id=course_id,
            before_revision=before_revision,
            after_revision=after_revision,
            plan_digest=plan_digest,
            after_decision=after_decision,
            after_counts=after_counts,
            refusal_code=refusal,
        )

    try:
        plan_items = _parse_plan_items(change_plan.get("items"))
        results = _parse_results(post_report.get("results"))
    except ValueError as exc:
        return _blocked_verification(
            course_id=course_id,
            before_revision=before_revision,
            after_revision=after_revision,
            plan_digest=plan_digest,
            after_decision=after_decision,
            after_counts=after_counts,
            refusal_code=str(exc),
        )

    by_row_id = {result["row_id"]: result for result in results}
    targets: list[TargetVerification] = []
    for item in plan_items:
        row_id = _row_id_from_finding_id(item["finding_id"], course_id)
        result = by_row_id.get(row_id)
        targets.append(_target_result(item, result))

    baseline_row_ids = {
        _row_id_from_finding_id(item["finding_id"], course_id)
        for item in plan_items
    }
    new_blocking = tuple(
        f"{course_id}:{result['row_id']}"
        for result in results
        if result["state"] in _BLOCKING_STATES
        and result["row_id"] not in baseline_row_ids
    )
    refusal = _verification_refusal(targets, new_blocking)
    return PublicCoursePostChangeVerification(
        course_id=course_id,
        before_revision=before_revision,
        after_revision=after_revision,
        plan_digest=plan_digest,
        after_decision=after_decision,
        after_counts=after_counts,
        targets=tuple(targets),
        new_blocking_findings=new_blocking,
        refusal_code=refusal,
    )


def _validate_inputs(
    *,
    change_plan: Mapping[str, object],
    post_report: Mapping[str, object],
    course_id: str,
    before_revision: str | None,
    after_revision: str | None,
    plan_digest: str | None,
) -> str | None:
    if change_plan.get("public_course_change_plan_version") != (
        PUBLIC_COURSE_CHANGE_PLAN_VERSION
    ):
        return "unsupported_change_plan_version"
    if post_report.get("claude_course_adapter_version") != _ADAPTER_VERSION:
        return "unsupported_adapter_version"
    if change_plan.get("decision") != "ready_for_human_approval":
        return "change_plan_incomplete"
    if not plan_digest:
        return "plan_digest_missing"
    if post_report.get("course_id") != course_id:
        return "course_id_mismatch"
    if not before_revision or not after_revision:
        return "course_revision_missing"
    if before_revision == after_revision:
        return "course_revision_unchanged"
    if post_report.get("offline") is not False:
        return "post_report_offline"
    if post_report.get("refusal_code") is not None:
        return "post_report_refused"
    if not isinstance(post_report.get("results"), list):
        return "post_results_missing"
    return None


def _parse_plan_items(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("change_plan_items_missing")
    items: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("change_plan_item_invalid")
        required = {
            "finding_id",
            "lesson_id",
            "claim_index",
            "state",
            "disposition",
        }
        if not required.issubset(item):
            raise ValueError("change_plan_item_invalid")
        if str(item["disposition"]) not in {
            HumanDisposition.RESOLVED.value,
            HumanDisposition.ACCEPTED.value,
        }:
            raise ValueError("change_plan_item_not_actionable")
        items.append(item)
    return tuple(items)


def _parse_results(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError("post_results_missing")
    results: list[dict[str, object]] = []
    seen_row_ids: set[str] = set()
    for result in value:
        if not isinstance(result, dict):
            raise ValueError("post_result_invalid")
        locator = result.get("locator")
        if not isinstance(locator, dict):
            raise ValueError("post_result_invalid")
        row_id = result.get("row_id")
        if not isinstance(row_id, str) or not row_id:
            raise ValueError("post_result_invalid")
        if row_id in seen_row_ids:
            raise ValueError("post_result_duplicate")
        seen_row_ids.add(row_id)
        state = result.get("state")
        if not isinstance(state, str) or not state:
            raise ValueError("post_result_invalid")
        results.append(
            {
                "row_id": row_id,
                "state": state,
                "reason_code": result.get("reason_code", "unavailable"),
                "lesson_id": locator.get("lesson_id"),
                "claim_index": locator.get("claim_index"),
            }
        )
    return tuple(results)


def _target_result(
    item: Mapping[str, object],
    result: Mapping[str, object] | None,
) -> TargetVerification:
    finding_id = str(item["finding_id"])
    lesson_id = str(item["lesson_id"])
    claim_index = int(item["claim_index"])
    disposition = HumanDisposition(str(item["disposition"]))
    before_state = str(item["state"])
    if result is None:
        return TargetVerification(
            finding_id=finding_id,
            lesson_id=lesson_id,
            claim_index=claim_index,
            disposition=disposition,
            before_state=before_state,
            after_state=None,
            outcome="target_missing",
            reason_code="post_result_missing",
        )
    if (
        result["lesson_id"] != lesson_id
        or result["claim_index"] != claim_index
    ):
        return TargetVerification(
            finding_id=finding_id,
            lesson_id=lesson_id,
            claim_index=claim_index,
            disposition=disposition,
            before_state=before_state,
            after_state=str(result["state"]),
            outcome="target_locator_changed",
            reason_code="post_locator_mismatch",
        )
    after_state = str(result["state"])
    if disposition is HumanDisposition.ACCEPTED:
        if after_state in _BLOCKING_STATES:
            outcome = "accepted_risk_regressed"
            reason_code = "accepted_risk_blocking"
        else:
            outcome = "accepted_risk_rechecked"
            reason_code = "accepted_risk_visible"
    elif after_state in _RECOVERY_STATES.get(before_state, frozenset()):
        outcome = "target_recovered"
        reason_code = "target_state_improved"
    else:
        outcome = "target_not_recovered"
        reason_code = str(result["reason_code"])
    return TargetVerification(
        finding_id=finding_id,
        lesson_id=lesson_id,
        claim_index=claim_index,
        disposition=disposition,
        before_state=before_state,
        after_state=after_state,
        outcome=outcome,
        reason_code=reason_code,
    )


def _verification_refusal(
    targets: list[TargetVerification],
    new_blocking: tuple[str, ...],
) -> str | None:
    if any(target.outcome == "target_missing" for target in targets):
        return "target_missing"
    if any(target.outcome == "target_locator_changed" for target in targets):
        return "target_locator_changed"
    if any(target.outcome == "target_not_recovered" for target in targets):
        return "target_not_recovered"
    if any(target.outcome == "accepted_risk_regressed" for target in targets):
        return "accepted_risk_regressed"
    if new_blocking:
        return "new_blocking_finding"
    return None


def _row_id_from_finding_id(finding_id: str, course_id: str) -> str:
    prefix = f"{course_id}:"
    if not finding_id.startswith(prefix):
        return f"invalid:{finding_id}"
    return finding_id[len(prefix):]


def _blocked_verification(
    *,
    course_id: str,
    before_revision: str | None,
    after_revision: str | None,
    plan_digest: str | None,
    after_decision: str,
    after_counts: dict[str, int | bool],
    refusal_code: str,
) -> PublicCoursePostChangeVerification:
    return PublicCoursePostChangeVerification(
        course_id=course_id,
        before_revision=before_revision,
        after_revision=after_revision,
        plan_digest=plan_digest,
        after_decision=after_decision,
        after_counts=after_counts,
        targets=(),
        new_blocking_findings=(),
        refusal_code=refusal_code,
    )


def _counts(value: object) -> dict[str, int | bool]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, (int, bool))
    }


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\n" in value:
        return None
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _safe_text(value)


def post_change_json(
    verification: PublicCoursePostChangeVerification,
) -> str:
    """Serialize a post-change verification result."""

    return json.dumps(verification.to_dict(), indent=2, sort_keys=True) + "\n"
