"""Create a safe starter declarative scenario pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


STARTER_PACK = {
    "pack_version": 1,
    "scenario_id": "custom-scenario",
    "title": "Custom synthetic scenario",
    "description": "Replace this description with a synthetic scenario purpose.",
    "dimension": "evidence_completeness",
    "available_tools": ["lookup_record"],
    "requirements": [
        {
            "requirement_id": "tool:lookup_record",
            "description": "Observe the declared lookup tool.",
            "evidence_type": "tool_call",
        },
        {
            "requirement_id": "abstain:when-evidence-insufficient",
            "description": "Abstain when the synthetic evidence is insufficient.",
            "evidence_type": "agent_behaviour",
        },
    ],
    "tools": [
        {
            "name": "lookup_record",
            "result_status": "not_found",
            "result_id": "custom-tool-result-001",
            "side_effect_id": None,
            "requires_authorization": False,
            "output_flags": [],
        }
    ],
    "faults": [],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a starter synthetic declarative scenario pack."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario-id", default="custom-scenario")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if args.output.exists() and not args.force:
        print(
            "Refusing to overwrite an existing scenario pack; use --force deliberately."
        )
        return 1
    pack = dict(STARTER_PACK)
    pack["scenario_id"] = args.scenario_id
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n")
    print(f"Created starter scenario pack: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
