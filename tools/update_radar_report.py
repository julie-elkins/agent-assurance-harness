"""Build a bounded metadata-only update-radar worklist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VERSION = 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a metadata-only worklist for public-source review."
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--inbox", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    registry = _load_object(args.registry, "registry")
    current = _load_object(args.current, "current") if args.current else {}
    previous = _load_object(args.previous, "previous") if args.previous else {}
    inbox = _load_object(args.inbox, "inbox") if args.inbox else {}
    report = build_report(registry, current, previous, inbox)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(to_markdown(report) if args.markdown else serialized, end="")
    return int(args.fail_on_findings and bool(report["findings"]))


def build_report(
    registry: dict[str, Any],
    current: dict[str, Any],
    previous: dict[str, Any],
    inbox: dict[str, Any],
) -> dict[str, Any]:
    sources = registry.get("sources", [])
    if not isinstance(sources, list) or not sources:
        return _blocked("registry_missing_or_empty")

    current_by_id = _records_by_id(current)
    previous_by_id = _records_by_id(previous)
    findings: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            return _blocked("invalid_source_record")
        source_id = _safe_id(source.get("source_id"))
        if source_id is None:
            return _blocked("source_id_missing")
        current_record = current_by_id.get(source_id)
        previous_record = previous_by_id.get(source_id)
        strategy = str(source.get("refresh_strategy", "manual_official_review"))
        state = "not_evaluated"
        if strategy == "metadata_hash" and current_record:
            digest = current_record.get("content_digest")
            previous_digest = (
                previous_record.get("content_digest") if previous_record else None
            )
            if not digest:
                state = "not_evaluated"
            elif previous_digest is None or digest != previous_digest:
                state = "review_required"
            else:
                state = "no_change_observed"
        elif strategy == "manual_official_review":
            state = "review_required"
        row = {
            "source_id": source_id,
            "authority": str(source.get("authority", "unknown")),
            "source_type": str(source.get("source_type", "unknown")),
            "trust_tier": str(source.get("trust_tier", "candidate")),
            "refresh_strategy": strategy,
            "url": str(source.get("url", "")),
            "targets": _safe_string_list(source.get("targets")),
            "state": state,
            "current_digest": _safe_digest(current_record),
            "previous_digest": _safe_digest(previous_record),
        }
        source_rows.append(row)
        if state in {"review_required", "not_evaluated"}:
            findings.append(
                {
                    "finding_id": f"source:{source_id}",
                    "kind": "official_source_review",
                    "state": state,
                    "source_id": source_id,
                    "targets": row["targets"],
                    "url": row["url"],
                    "action": "human_review_source_and_affected_claims",
                }
            )

    inbox_items = inbox.get("items", [])
    if inbox_items and not isinstance(inbox_items, list):
        return _blocked("invalid_inbox")
    inbox_rows: list[dict[str, Any]] = []
    for item in inbox_items or []:
        if not isinstance(item, dict):
            return _blocked("invalid_inbox_item")
        item_id = _safe_id(item.get("item_id"))
        url = item.get("url")
        if item_id is None or not isinstance(url, str) or not url.startswith("https://"):
            return _blocked("inbox_item_identity_invalid")
        row = {
            "item_id": item_id,
            "url": url,
            "label": str(item.get("label", "unlabelled lead")),
            "scope": _safe_string_list(item.get("scope")),
            "trust_tier": "lead",
            "state": "review_required",
        }
        inbox_rows.append(row)
        findings.append(
            {
                "finding_id": f"inbox:{item_id}",
                "kind": "queued_social_lead",
                "state": "review_required",
                "item_id": item_id,
                "scope": row["scope"],
                "url": url,
                "action": "verify_against_authoritative_source",
            }
        )

    return {
        "update_radar_version": VERSION,
        "decision": "review_required" if findings else "no_action_identified",
        "sources": source_rows,
        "inbox": inbox_rows,
        "findings": findings,
        "diagnostics": {
            "source_bodies_stored": False,
            "linkedin_feed_scraped": False,
            "publication_authorized": False,
            "what_it_does_not_prove": (
                "A source change does not prove a course update is required, "
                "and an unchanged digest does not prove every claim remains valid."
            ),
        },
    }


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Update Radar",
        "",
        f"Decision: `{report.get('decision', 'blocked').upper()}`",
        "",
        f"- Official sources: `{len(report.get('sources', []))}`",
        f"- Queued leads: `{len(report.get('inbox', []))}`",
        f"- Findings: `{len(report.get('findings', []))}`",
        "",
        "| Source or lead | Tier | State | Targets |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("sources", []):
        lines.append(
            f"| `{row['source_id']}` | `{row['trust_tier']}` | "
            f"`{row['state']}` | `{', '.join(row['targets']) or 'none'}` |"
        )
    for row in report.get("inbox", []):
        lines.append(
            f"| `{row['item_id']}` | `lead` | `review_required` | "
            f"`{', '.join(row['scope']) or 'none'}` |"
        )
    lines.extend(
        [
            "",
            "This report is a review queue. It does not edit, approve, or publish content.",
        ]
    )
    return "\n".join(lines)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{label}_load_failed") from error
    if not isinstance(value, dict):
        raise SystemExit(f"{label}_object_required")
    return value


def _records_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = report.get("sources", [])
    if not isinstance(records, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("source_id"), str):
            result[record["source_id"]] = record
    return result


def _safe_digest(record: dict[str, Any] | None) -> str | None:
    if not record:
        return None
    digest = record.get("content_digest")
    return digest if isinstance(digest, str) and digest.startswith("sha256:") else None


def _safe_id(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 120:
        return None
    return value


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item][:50]


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "update_radar_version": VERSION,
        "decision": "blocked",
        "sources": [],
        "inbox": [],
        "findings": [
            {
                "finding_id": "radar:input",
                "kind": "input_validation",
                "state": "blocked",
                "reason": reason,
                "action": "repair_input_and_rerun",
            }
        ],
        "diagnostics": {
            "source_bodies_stored": False,
            "linkedin_feed_scraped": False,
            "publication_authorized": False,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
