"""Check the required contract markers in a pinned reusable action.

The check is intentionally structural: it proves that the reviewed action revision
contains the inputs and runner wiring required by the consumer contract without
exporting the action source or treating unrelated implementation text as a contract.
"""

from __future__ import annotations

from dataclasses import dataclass


ACTION_PARITY_VERSION = 1

REQUIRED_ACTION_MARKERS = (
    "consumer-policy-manifest:",
    "ASSURANCE_CONSUMER_POLICY_MANIFEST:",
    '--consumer-policy-manifest "$ASSURANCE_CONSUMER_POLICY_MANIFEST"',
    "tools/reusable_action_runner.py",
)


@dataclass(frozen=True)
class ActionParityReport:
    """Metadata-only result for one action revision."""

    passed: bool
    present_markers: tuple[str, ...]
    missing_markers: tuple[str, ...]

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        """Return stable reasons without exposing action source."""

        if self.passed:
            return ()
        return tuple(f"missing_action_marker:{marker}" for marker in self.missing_markers)

    def to_dict(self) -> dict[str, object]:
        """Return a safe report containing markers and statuses only."""

        return {
            "action_parity_version": ACTION_PARITY_VERSION,
            "passed": self.passed,
            "required_markers": list(REQUIRED_ACTION_MARKERS),
            "present_markers": list(self.present_markers),
            "missing_markers": list(self.missing_markers),
            "failure_reasons": list(self.failure_reasons),
            "diagnostics": {
                "warnings": [
                    "Content parity checks required action behavior at the pinned "
                    "revision; it does not prove hosted-runner availability."
                ],
                "what_it_does_not_show": (
                    "It does not prove live-provider quality, deployment behavior, "
                    "or that unrelated action code is safe."
                ),
            },
        }


def verify_action_text(action_text: str) -> ActionParityReport:
    """Verify the minimum reusable-action contract without returning its source."""

    present = tuple(
        marker for marker in REQUIRED_ACTION_MARKERS if marker in action_text
    )
    missing = tuple(
        marker for marker in REQUIRED_ACTION_MARKERS if marker not in action_text
    )
    return ActionParityReport(
        passed=not missing,
        present_markers=present,
        missing_markers=missing,
    )
