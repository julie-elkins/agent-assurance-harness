"""Generate the synthetic candidate replay used by the Phase 12 CI demonstration."""

from __future__ import annotations

import json
from dataclasses import replace

from agent_reliability_lab.replay import HarnessChangeManifest
from recorder_adapter import replay_file


def main() -> int:
    """Emit a passing candidate replay with a distinct harness manifest."""

    replay = replay_file()
    candidate = replace(
        replay,
        harness_change=HarnessChangeManifest(
            change_id="candidate-guardrails-2026-10-20",
            components=("guardrails", "tool_guidance"),
        ),
    )
    print(json.dumps(candidate.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
