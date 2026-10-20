"""Deliberately degraded consumer adapter for the expected blocking control."""

from __future__ import annotations

import json
import sys

from guarded_adapter import response_for


def main() -> int:
    for line in sys.stdin:
        request = json.loads(line)
        response = response_for(
            str(request["scenario_id"]),
            regress=True,
        )
        print(json.dumps(response, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
