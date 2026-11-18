"""Report a constrained, synthetic Pareto frontier without choosing a winner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_reliability_lab.pareto import (
    CandidateEvaluation,
    ParetoConstraints,
    compare_candidates,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "examples" / "pareto-candidate-comparison" / "candidates.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or not isinstance(value.get("candidates"), list):
        raise ValueError("input must contain a candidates list")
    return value


def run_report(path: Path) -> dict[str, object]:
    source = _load(path)
    raw_constraints = source.get("constraints", {})
    if not isinstance(raw_constraints, dict):
        raise ValueError("constraints must be an object")
    candidates = tuple(
        CandidateEvaluation.from_dict(value)
        for value in source["candidates"]
        if isinstance(value, dict)
    )
    if len(candidates) != len(source["candidates"]):
        raise ValueError("each candidate must be an object")
    comparison = compare_candidates(
        candidates,
        constraints=ParetoConstraints(**raw_constraints),
    )
    return {
        "comparison_id": source.get("comparison_id", "synthetic-candidate-comparison"),
        "synthetic_only": True,
        "candidate_count": len(candidates),
        "comparison": comparison.to_dict(),
    }


def main() -> int:
    args = _parse_args()
    try:
        report = run_report(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(
            f"pareto_candidate_report_refused: {type(error).__name__}"
        ) from error
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
