from datetime import datetime, timezone

from agent_reliability_lab.public_sources import (
    PUBLIC_SOURCE_SPECS,
    refresh_public_sources,
)


class FakeResponse:
    def __init__(self, url: str, body: bytes, status: int = 200):
        self._url = url
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def geturl(self):
        return self._url

    def read(self, limit):
        return self._body[:limit]


def test_refresh_hashes_real_source_bytes_but_emits_metadata_only():
    def opener(request, *, timeout):
        del timeout
        return FakeResponse(request.full_url, b"synthetic public response")

    report = refresh_public_sources(
        opener=opener,
        now=datetime(2026, 10, 21, tzinfo=timezone.utc),
    )

    assert report.passed
    assert [record.source_id for record in report.records] == [
        spec.source_id for spec in PUBLIC_SOURCE_SPECS
    ]
    assert all(record.content_digest.startswith("sha256:") for record in report.records)
    assert all(record.byte_count > 0 for record in report.records)
    assert "body" not in report.to_dict()


def test_refresh_refuses_redirect_to_non_official_host():
    def opener(request, *, timeout):
        del request, timeout
        return FakeResponse("https://example.invalid/", b"private-looking response")

    report = refresh_public_sources(opener=opener)

    assert not report.passed
    assert report.records == ()
    assert len(report.refusals) == len(PUBLIC_SOURCE_SPECS)
    assert all(refusal.error == "unapproved_source_host" for refusal in report.refusals)


def test_refresh_refuses_oversized_response():
    def opener(request, *, timeout):
        del timeout
        return FakeResponse(request.full_url, b"0123456789")

    report = refresh_public_sources(opener=opener, max_bytes=4)

    assert not report.passed
    assert all(refusal.error == "response_too_large" for refusal in report.refusals)
