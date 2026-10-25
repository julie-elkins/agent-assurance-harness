"""Local client for the metadata-only hosted assurance control plane.

Design rules:

1. Read AWS credentials only through an explicitly named AWS CLI profile; never accept
   credential values as CLI arguments or include them in a refusal.
2. Sign only HTTPS API Gateway endpoints in the caller-selected AWS Region and only the
   two documented control-plane routes.
3. Build submissions from the validated run-manifest model so prompts, tool payloads,
   provider output, and private paths cannot enter the hosted request.
4. Return bounded metadata views rather than echoing arbitrary hosted responses.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .run_manifest import RunManifest, load_current_revisions, load_manifest


# MODELLING ASSUMPTION: one local control-plane request should finish within twenty
# seconds. A caller that needs a different ceiling must change this constant deliberately
# rather than allowing an unbounded credential or network subprocess.
DEFAULT_TIMEOUT_SECONDS = 20.0
_AWS_CREDENTIAL_TIMEOUT_SECONDS = 10.0
_AWS_CLI = "aws"
_AWS_SERVICE = "execute-api"
_API_VERSION_PATH = "/v1"
_PROFILE_PATTERN = re.compile(r"^[^\r\n]{1,128}$")
_REGION_PATTERN = re.compile(r"^[a-z0-9-]{1,32}$")
_PROVIDERS = frozenset({"anthropic", "openai"})
_SAFE_PROVIDER_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


@dataclass(frozen=True)
class AwsCredentials:
    """Temporary credentials exported by the AWS CLI credential process."""

    access_key_id: str
    secret_access_key: str
    session_token: str | None


@dataclass(frozen=True)
class HostedRequest:
    """The signed request passed to the injected or real HTTP transport."""

    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class HostedResponse:
    """A bounded HTTP result with either a JSON object or a structured refusal."""

    status_code: int | None
    body: dict[str, object] | None
    refusal: dict[str, object] | None = None

    @property
    def ok(self) -> bool:
        """Return whether the response was a successful JSON object."""

        return self.status_code is not None and 200 <= self.status_code < 300 and (
            self.body is not None
        )


Transport = Callable[[HostedRequest], HostedResponse]
CredentialLoader = Callable[[str, str], tuple[AwsCredentials | None, dict[str, object] | None]]


def _refusal(error: str, message: str, guidance: str) -> dict[str, object]:
    return {
        "error": error,
        "message": message,
        "guidance": guidance,
    }


def _validate_profile(profile: str) -> str:
    if not isinstance(profile, str) or _PROFILE_PATTERN.fullmatch(profile) is None:
        raise ValueError(
            "aws_profile must be a non-empty profile name without newlines."
        )
    return profile


def _validate_region(region: str) -> str:
    if not isinstance(region, str) or _REGION_PATTERN.fullmatch(region) is None:
        raise ValueError("region must be a bounded AWS Region identifier.")
    return region


def validate_endpoint(endpoint: str, region: str) -> str:
    """Validate and normalise one API Gateway endpoint without contacting it."""

    _validate_region(region)
    parsed = urllib.parse.urlsplit(endpoint)
    host = parsed.hostname
    expected_suffix = f".execute-api.{region}.amazonaws.com"
    if (
        parsed.scheme != "https"
        or not host
        or not host.endswith(expected_suffix)
        or not parsed.netloc.endswith(expected_suffix)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.rstrip("/").endswith(_API_VERSION_PATH)
    ):
        raise ValueError(
            "endpoint must be an HTTPS API Gateway URL ending in the selected "
            "Region and /v1, without credentials, query parameters, or fragments."
        )
    return endpoint.rstrip("/")


def load_aws_cli_credentials(
    profile: str,
    region: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[AwsCredentials | None, dict[str, object] | None]:
    """Export temporary credentials without exposing CLI output or secret values."""

    try:
        _validate_profile(profile)
        _validate_region(region)
    except ValueError as error:
        return None, _refusal(
            "aws_profile_invalid",
            "The AWS credential profile or Region is invalid.",
            str(error),
        )
    try:
        completed = runner(
            [
                _AWS_CLI,
                "configure",
                "export-credentials",
                "--profile",
                profile,
                "--format",
                "process",
                "--region",
                region,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_AWS_CREDENTIAL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return None, _refusal(
            "aws_cli_missing",
            "The AWS CLI is not installed.",
            "Install the AWS CLI and retry with an authenticated profile.",
        )
    except subprocess.TimeoutExpired:
        return None, _refusal(
            "aws_credentials_timeout",
            "The AWS CLI did not return temporary credentials in time.",
            "Complete the AWS SSO login and retry.",
        )
    except OSError:
        return None, _refusal(
            "aws_credentials_unavailable",
            "The AWS CLI credential process could not be started.",
            "Check the local AWS CLI installation and profile configuration.",
        )
    if completed.returncode != 0:
        return None, _refusal(
            "aws_credentials_unavailable",
            "The AWS CLI could not export temporary credentials.",
            "Run aws sso login for the named profile and retry.",
        )
    try:
        data = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return None, _refusal(
            "aws_credentials_invalid",
            "The AWS CLI returned an invalid credential record.",
            "Refresh the named AWS profile and retry.",
        )
    if not isinstance(data, dict):
        return None, _refusal(
            "aws_credentials_invalid",
            "The AWS CLI credential record was not an object.",
            "Refresh the named AWS profile and retry.",
        )
    access_key_id = data.get("AccessKeyId")
    secret_access_key = data.get("SecretAccessKey")
    session_token = data.get("SessionToken")
    if (
        not isinstance(access_key_id, str)
        or not access_key_id
        or not isinstance(secret_access_key, str)
        or not secret_access_key
        or (session_token is not None and not isinstance(session_token, str))
    ):
        return None, _refusal(
            "aws_credentials_invalid",
            "The AWS CLI credential record was incomplete.",
            "Refresh the named AWS profile and retry.",
        )
    return (
        AwsCredentials(access_key_id, secret_access_key, session_token),
        None,
    )


def _signing_key(secret: str, date: str, region: str) -> bytes:
    key_date = hmac.new(
        ("AWS4" + secret).encode("utf-8"),
        date.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    key_region = hmac.new(key_date, region.encode("utf-8"), hashlib.sha256).digest()
    key_service = hmac.new(key_region, _AWS_SERVICE.encode("utf-8"), hashlib.sha256)
    return hmac.new(key_service.digest(), b"aws4_request", hashlib.sha256).digest()


def _canonical_uri(path: str) -> str:
    return urllib.parse.quote(path or "/", safe="/-_.~")


def sign_request(
    method: str,
    url: str,
    body: bytes,
    credentials: AwsCredentials,
    region: str,
    *,
    now: datetime | None = None,
) -> HostedRequest:
    """Create an AWS SigV4 request using only in-memory credential values."""

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("signed request URL must be HTTPS and have no query or fragment.")
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    short_date = timestamp.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    host = parsed.netloc
    headers = {
        "content-type": "application/json",
        "host": host,
        "x-amz-date": amz_date,
    }
    if credentials.session_token:
        headers["x-amz-security-token"] = credentials.session_token
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(
        f"{name}:{' '.join(headers[name].strip().split())}\n"
        for name in sorted(headers)
    )
    canonical_request = "\n".join(
        (
            method.upper(),
            _canonical_uri(parsed.path),
            urllib.parse.urlencode(
                urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            ),
            canonical_headers,
            signed_headers,
            payload_hash,
        )
    )
    scope = f"{short_date}/{region}/{_AWS_SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        (
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        )
    )
    signature = hmac.new(
        _signing_key(credentials.secret_access_key, short_date, region),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers["authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={credentials.access_key_id}/{scope},"
        f"SignedHeaders={signed_headers},Signature={signature}"
    )
    return HostedRequest(method.upper(), url, headers, body)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so the signed request cannot change hosts."""

    def redirect_request(self, request, file, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "redirects are disabled",
            headers,
            None,
        )


_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _json_object(value: bytes) -> dict[str, object] | None:
    try:
        parsed = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _http_transport(request: HostedRequest) -> HostedResponse:
    """Send one bounded request and discard bodies that are not safe JSON objects."""

    http_request = urllib.request.Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method=request.method,
    )
    try:
        with _OPENER.open(http_request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            body = response.read()
            parsed = _json_object(body)
            if parsed is None:
                return HostedResponse(
                    response.status,
                    None,
                    _refusal(
                        "hosted_response_invalid",
                        "The hosted service did not return a JSON object.",
                        "Inspect the hosted service health before retrying.",
                    ),
                )
            return HostedResponse(response.status, parsed)
    except urllib.error.HTTPError as error:
        body = error.read()
        parsed = _json_object(body)
        if parsed is not None:
            return HostedResponse(error.code, parsed)
        return HostedResponse(
            error.code,
            None,
            _refusal(
                "hosted_http_error",
                "The hosted service returned a non-JSON HTTP error.",
                "Inspect the hosted service status without exporting the response body.",
            ),
        )
    except (OSError, urllib.error.URLError, TimeoutError):
        return HostedResponse(
            None,
            None,
            _refusal(
                "hosted_transport_failed",
                "The hosted request did not complete.",
                "Check the AWS Region, endpoint, SSO profile, and service status.",
            ),
        )


def _route_url(endpoint: str, route: str) -> str:
    if route not in {"/reauthorizations"} and not route.startswith("/runs/"):
        raise ValueError("route is not part of the hosted control-plane contract.")
    return endpoint.rstrip("/") + route


def safe_submission_payload(
    manifest: RunManifest,
    current_revisions: Mapping[str, str],
    *,
    provider: str | None = None,
) -> dict[str, object]:
    """Build a provider-neutral metadata payload from validated model objects."""

    if provider is not None and provider not in _PROVIDERS:
        raise ValueError("provider must be openai or anthropic.")
    manifest_data = manifest.to_dict()
    if provider is not None:
        # The adapter bridge changes only stable identifiers. It deliberately does not
        # copy provider responses or introduce a provider-specific payload shape.
        manifest_data["provider"] = provider
        manifest_data["agent_id"] = f"{provider}-mock"
        manifest_data["model"] = f"{provider}-synthetic"
    budget = manifest_data.get("budget")
    if isinstance(budget, dict):
        # `within_limits` is a derived local report field, not an input dependency.
        # Sending it would make the local serializer and hosted contract drift apart.
        budget.pop("within_limits", None)
    return {
        "manifest": manifest_data,
        "current_revisions": dict(current_revisions),
    }


def load_safe_submission(
    manifest_path: Path,
    current_revisions_path: Path,
    *,
    provider: str | None = None,
) -> dict[str, object]:
    """Load and validate the public synthetic manifest inputs."""

    return safe_submission_payload(
        load_manifest(str(manifest_path)),
        load_current_revisions(str(current_revisions_path)),
        provider=provider,
    )


def decision_view(value: Mapping[str, object]) -> dict[str, object]:
    """Return only the stable decision fields needed by a local caller."""

    allowed = {
        "run_id",
        "audit_id",
        "status",
        "supports_decision",
        "changed_dependencies",
        "reasons",
        "required_action",
        "recorded_at",
        "expires_at_epoch",
    }
    return {key: value[key] for key in sorted(allowed) if key in value}


@dataclass
class HostedControlPlaneClient:
    """Submit and retrieve metadata-only decisions from the hosted service."""

    endpoint: str
    profile: str
    region: str
    credentials_loader: CredentialLoader = load_aws_cli_credentials
    transport: Transport = _http_transport

    def __post_init__(self) -> None:
        self.endpoint = validate_endpoint(self.endpoint, self.region)
        _validate_profile(self.profile)

    def _request(
        self,
        method: str,
        route: str,
        body: dict[str, object] | None = None,
    ) -> HostedResponse:
        credentials, refusal = self.credentials_loader(self.profile, self.region)
        if refusal is not None or credentials is None:
            return HostedResponse(None, None, refusal)
        payload = (
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if body is not None
            else b""
        )
        try:
            request = sign_request(
                method,
                _route_url(self.endpoint, route),
                payload,
                credentials,
                self.region,
            )
        except ValueError as error:
            return HostedResponse(
                None,
                None,
                _refusal(
                    "hosted_request_invalid",
                    "The hosted request could not be constructed safely.",
                    str(error),
                ),
            )
        return self.transport(request)

    def submit(self, payload: dict[str, object]) -> HostedResponse:
        """Submit one metadata-only manifest and current revision map."""

        return self._request("POST", "/reauthorizations", payload)

    def get_latest(self, run_id: str) -> HostedResponse:
        """Retrieve one bounded decision by its validated run identifier."""

        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", run_id):
            return HostedResponse(
                None,
                None,
                _refusal(
                    "run_id_invalid",
                    "The run identifier is not valid.",
                    "Use letters, numbers, periods, underscores, colons, or hyphens.",
                ),
            )
        return self._request("GET", f"/runs/{urllib.parse.quote(run_id, safe='-_.:')}")


def build_local_run(
    client: HostedControlPlaneClient,
    manifest_path: Path,
    current_revisions_path: Path,
    *,
    provider: str | None = None,
) -> dict[str, object]:
    """Submit one safe payload and return its bounded decision view."""

    payload = load_safe_submission(
        manifest_path,
        current_revisions_path,
        provider=provider,
    )
    submission = client.submit(payload)
    result: dict[str, object] = {
        "provider": provider or str(payload["manifest"]["provider"]),
    }
    if submission.refusal is not None:
        result["refusal"] = submission.refusal
        return result
    if submission.body is None:
        result["refusal"] = _refusal(
            "hosted_response_missing",
            "The hosted service returned no decision body.",
            "Inspect the hosted service status before retrying.",
        )
        return result
    hosted_refusal = submission.body.get("refusal")
    if isinstance(hosted_refusal, dict):
        result["refusal"] = hosted_refusal
        return result
    result["submission"] = decision_view(submission.body)
    run_id = submission.body.get("run_id")
    if not isinstance(run_id, str):
        result["refusal"] = _refusal(
            "hosted_response_incomplete",
            "The hosted service response did not include a run identifier.",
            "Inspect the hosted service contract before retrying.",
        )
        return result
    latest = client.get_latest(run_id)
    if latest.refusal is not None:
        result["refusal"] = latest.refusal
    elif latest.body is not None:
        hosted_refusal = latest.body.get("refusal")
        if isinstance(hosted_refusal, dict):
            result["refusal"] = hosted_refusal
        else:
            result["latest"] = decision_view(latest.body)
    else:
        result["refusal"] = _refusal(
            "hosted_response_missing",
            "The hosted service returned no latest decision body.",
            "Inspect the hosted service status before retrying.",
        )
    return result


__all__ = [
    "AwsCredentials",
    "HostedControlPlaneClient",
    "HostedRequest",
    "HostedResponse",
    "build_local_run",
    "decision_view",
    "load_aws_cli_credentials",
    "load_safe_submission",
    "safe_submission_payload",
    "sign_request",
    "validate_endpoint",
]
