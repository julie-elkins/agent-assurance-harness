import importlib.util
from pathlib import Path


_TOOL_PATH = Path(__file__).parents[2] / "tools" / "update_radar_report.py"
_SPEC = importlib.util.spec_from_file_location("update_radar_report", _TOOL_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
build_report = _MODULE.build_report


def test_update_radar_marks_changed_official_source_and_queued_lead():
    registry = {
        "sources": [
            {
                "source_id": "official",
                "authority": "test-official",
                "source_type": "official-documentation",
                "trust_tier": "confirmed",
                "refresh_strategy": "metadata_hash",
                "url": "https://example.test/docs",
                "targets": ["course"],
            },
            {
                "source_id": "manual",
                "authority": "test-official",
                "source_type": "official-documentation",
                "trust_tier": "confirmed",
                "refresh_strategy": "manual_official_review",
                "url": "https://example.test/manual",
                "targets": ["guide"],
            },
        ]
    }
    current = {
        "sources": [
            {"source_id": "official", "content_digest": "sha256:new"}
        ]
    }
    previous = {
        "sources": [
            {"source_id": "official", "content_digest": "sha256:old"}
        ]
    }
    inbox = {
        "items": [
            {
                "item_id": "linkedin-1",
                "url": "https://lnkd.in/example",
                "label": "candidate",
                "scope": ["course"],
            }
        ]
    }

    report = build_report(registry, current, previous, inbox)

    assert report["decision"] == "review_required"
    assert {row["state"] for row in report["sources"]} == {
        "review_required"
    }
    assert report["inbox"][0]["trust_tier"] == "lead"
    assert report["diagnostics"]["linkedin_feed_scraped"] is False


def test_update_radar_preserves_missing_digest_as_not_evaluated():
    registry = {
        "sources": [
            {
                "source_id": "official",
                "authority": "test-official",
                "source_type": "official-documentation",
                "trust_tier": "confirmed",
                "refresh_strategy": "metadata_hash",
                "url": "https://example.test/docs",
                "targets": ["course"],
            }
        ]
    }

    report = build_report(registry, {}, {}, {})

    assert report["decision"] == "review_required"
    assert report["sources"][0]["state"] == "not_evaluated"
    assert report["findings"][0]["state"] == "not_evaluated"
