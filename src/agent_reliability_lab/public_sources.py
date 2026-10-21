"""Bounded metadata refresh for official public documentation sources.

The refresh path reads real public documentation only when a caller explicitly
invokes it. It never stores or emits the fetched body. The resulting manifest
contains the URL, retrieval time, byte count, and SHA-256 fingerprint needed by
the content-assurance agent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PUBLIC_SOURCE_REFRESH_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_BYTES = 2_000_000
OFFICIAL_DOCUMENTATION_HOSTS = frozenset(
    {
        "docs.aws.amazon.com",
        "docs.anthropic.com",
        "anthropic.com",
        "www.anthropic.com",
        "platform.claude.com",
        "developers.openai.com",
        "platform.openai.com",
    }
)


@dataclass(frozen=True)
class PublicSourceSpec:
    """One fixed official documentation source that may be refreshed."""

    source_id: str
    authority: str
    source_url: str


PUBLIC_SOURCE_SPECS = (
    PublicSourceSpec(
        source_id="aws-official-docs",
        authority="aws-official",
        source_url="https://docs.aws.amazon.com/",
    ),
    PublicSourceSpec(
        source_id="anthropic-official-docs",
        authority="anthropic-official",
        source_url="https://www.anthropic.com/docs",
    ),
    PublicSourceSpec(
        source_id="openai-official-docs",
        authority="openai-official",
        source_url="https://developers.openai.com/",
    ),
)


@dataclass(frozen=True)
class PublicSourceRecord:
    """Metadata for one successfully refreshed public source."""

    source_id: str
    authority: str
    source_url: str
    retrieved_at: str
    content_digest: str
    byte_count: int

    def to_dict(self) -> dict[str, object]:
        """Return metadata without the fetched documentation body."""

        return {
            "source_id": self.source_id,
            "authority": self.authority,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "content_digest": self.content_digest,
            "byte_count": self.byte_count,
        }


@dataclass(frozen=True)
class PublicSourceRefreshRefusal:
    """A metadata-only refusal for one source refresh."""

    source_id: str
    error: str
    guidance: str

    def to_dict(self) -> dict[str, str]:
        """Return a stable refusal shape."""

        return {
            "source_id": self.source_id,
            "error": self.error,
            "guidance": self.guidance,
        }


@dataclass(frozen=True)
class PublicSourceRefreshReport:
    """The result of an explicit official-source metadata refresh."""

    records: tuple[PublicSourceRecord, ...]
    refusals: tuple[PublicSourceRefreshRefusal, ...]

    @property
    def passed(self) -> bool:
        """Return true only when every fixed source refreshed successfully."""

        return not self.refusals and len(self.records) == len(PUBLIC_SOURCE_SPECS)

    def to_dict(self) -> dict[str, object]:
        """Return the checked-in-manifest shape without source content."""

        return {
            "public_source_refresh_version": PUBLIC_SOURCE_REFRESH_VERSION,
            "passed": self.passed,
            "sources": [record.to_dict() for record in self.records],
            "refusals": [refusal.to_dict() for refusal in self.refusals],
            "diagnostics": {
                "warnings": [
                    "The response bodies were hashed and discarded; this manifest "
                    "does not contain documentation text."
                ],
                "what_it_does_not_show": (
                    "It does not prove that the documentation is correct, that "
                    "a source is complete, or that a later request will see the "
                    "same bytes."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a human-readable metadata-only refresh summary."""

        lines = [
            "# Public Source Refresh",
            "",
            f"Decision: {'PASS' if self.passed else 'BLOCKED'}",
            "",
            "| Source | Retrieved | Bytes | Digest |",
            "| --- | --- | ---: | --- |",
        ]
        for record in self.records:
            lines.append(
                f"| `{record.source_id}` | `{record.retrieved_at}` | "
                f"{record.byte_count} | `{record.content_digest}` |"
            )
        if self.refusals:
            lines.extend(["", "Refusals:"])
            lines.extend(
                f"- `{refusal.source_id}`: `{refusal.error}`"
                for refusal in self.refusals
            )
        lines.extend(
            [
                "",
                "Response bodies were discarded; this summary contains metadata only.",
            ]
        )
        return "\n".join(lines)


def refresh_public_sources(
    *,
    opener: Callable[..., object] = urlopen,
    now: datetime | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> PublicSourceRefreshReport:
    """Fetch fixed official URLs and retain only bounded metadata."""

    if timeout_seconds <= 0 or max_bytes < 1:
        raise ValueError("Refresh limits must be positive.")
    retrieved_at = (now or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    ).isoformat()
    records: list[PublicSourceRecord] = []
    refusals: list[PublicSourceRefreshRefusal] = []
    for spec in PUBLIC_SOURCE_SPECS:
        try:
            _validate_official_url(spec.source_url)
            request = Request(
                spec.source_url,
                headers={"User-Agent": "agent-assurance-harness-source-refresh/1"},
            )
            with opener(request, timeout=timeout_seconds) as response:
                final_url = str(response.geturl())
                _validate_official_url(final_url)
                status = getattr(response, "status", 200)
                if status != 200:
                    raise ValueError(f"http_status_{status}")
                body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("response_too_large")
            records.append(
                PublicSourceRecord(
                    source_id=spec.source_id,
                    authority=spec.authority,
                    source_url=final_url,
                    retrieved_at=retrieved_at,
                    content_digest=_sha256(body),
                    byte_count=len(body),
                )
            )
        except (OSError, URLError, ValueError, TypeError) as error:
            refusals.append(
                PublicSourceRefreshRefusal(
                    source_id=spec.source_id,
                    error=(
                        type(error).__name__
                        if isinstance(error, (OSError, URLError))
                        else str(error)
                    ),
                    guidance=(
                        "Retry only against the fixed official URL and inspect the "
                        "metadata-only refusal before using the source."
                    ),
                )
            )
    return PublicSourceRefreshReport(tuple(records), tuple(refusals))


def _validate_official_url(value: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in OFFICIAL_DOCUMENTATION_HOSTS
        or parsed.username
        or parsed.password
    ):
        raise ValueError("unapproved_source_host")


def _sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()
