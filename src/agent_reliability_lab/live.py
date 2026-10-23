"""Opt-in live provider boundary for one synthetic scenario at a time.

Design rules:

1. The caller must opt in to network access and provide all usage ceilings explicitly.
2. Only official HTTPS endpoints are allowed; arbitrary URLs are not accepted.
3. Requests contain built-in synthetic identifiers only, never caller-supplied content.
4. Provider text is parsed in memory and discarded after identifier-only normalization.
5. Transport, retry, and provider failures become structured refusals without raw bodies.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Callable

from .environment import SimulatedToolEnvironment
from .external import DEFAULT_MAX_RESPONSE_BYTES
from .protocol import AdapterRefusal, AdapterRun, ScenarioRequest
from .providers import (
    ProviderLimits,
    ProviderPayloadError,
    _parse_usage,
    translate_provider_payload,
)


# FIELD CONVENTION: official provider endpoints and request fields follow the public
# provider API references. OpenAI Responses API:
# https://platform.openai.com/docs/api-reference/responses/create
# Anthropic Messages API:
# https://docs.anthropic.com/en/api/messages
_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/responses",
    "anthropic": "https://api.anthropic.com/v1/messages",
}
_CREDENTIALS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
_MAX_RESPONSE_BYTES = DEFAULT_MAX_RESPONSE_BYTES
_PLACEHOLDER_CREDENTIALS = frozenset(
    {
        "your-key-here",
        "replace-me",
        "replace-with-your-key",
    }
)
_LIVE_INSTRUCTIONS = (
    "You are producing a machine-checked, identifier-only event classification. "
    "Return exactly one JSON object and no Markdown, explanation, prose, prompts, "
    "tool arguments, tool-result payloads, messages, or hidden reasoning. "
    "For Anthropic, the JSON object must have exactly one key named content whose "
    "value is an array of safe events. A reliability classification event is shaped "
    "as {\"type\":\"reliability\",\"kind\":\"claim|answer|abstention|authorization|"
    "side_effect|operation_id|idempotency_key|reconciliation|action_digest\"}; "
    "Every classification except abstention requires an identifier field named id. "
    "A reconciliation classification also requires status, and an action_digest "
    "identifier must use the reviewed sha256 format. Emit at most one claim, "
    "answer, abstention, authorization, or side_effect classification per trace; "
    "omit a classification rather than repeating it. "
    "A tool event is either {\"type\":\"tool_use\",\"name\":\"synthetic-tool\","
    "\"id\":\"synthetic-call-id\"} or a matching {\"type\":\"tool_result\","
    "\"tool_use_id\":\"synthetic-call-id\",\"status\":\"ok|not_found|missing|"
    "unauthorized|timeout|confirmed\",\"evidence_id\":\"synthetic-evidence-id\"}. "
    "Use only identifiers already present in the request or stable synthetic "
    "identifiers; never invent prose."
)


HttpTransport = Callable[[str, dict[str, str], bytes, float], bytes]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so the fixed official endpoint cannot change hosts."""

    def redirect_request(self, request, file, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "provider redirects are disabled",
            headers,
            None,
        )


_LIVE_OPENER = urllib.request.build_opener(_NoRedirectHandler())


@dataclass(frozen=True)
class LiveProviderPolicy:
    """Explicit controls required before one live synthetic request."""

    provider_id: str
    model: str
    credential_env_var: str
    limits: ProviderLimits
    estimated_cost_usd_per_request: float
    allow_network: bool

    def validate(self) -> AdapterRefusal | None:
        """Return a refusal when live execution is not explicitly bounded."""

        expected_credential = _CREDENTIALS.get(self.provider_id)
        if expected_credential is None:
            return _refusal(
                "unsupported_provider",
                "The live provider is not supported.",
                "Use openai or anthropic.",
            )
        if self.credential_env_var != expected_credential:
            return _refusal(
                "invalid_credential_environment_variable",
                "The credential environment variable does not match the provider.",
                "Use the fixed provider credential name; do not pass a credential value.",
            )
        if not self.model or any(character.isspace() for character in self.model):
            return _refusal(
                "invalid_provider_model",
                "The provider model must be a non-empty identifier.",
                "Supply the provider model as a CLI value without whitespace.",
            )
        if not self.allow_network:
            return _refusal(
                "network_opt_in_required",
                "Live provider execution requires explicit network opt-in.",
                "Pass --allow-network only for an intentional local synthetic run.",
            )
        refusal = self.limits.validate()
        if refusal is not None:
            return refusal
        if self.limits.max_requests != 1:
            return _refusal(
                "single_request_limit_required",
                "The live boundary permits exactly one provider request per scenario.",
                "Set max_requests to 1; retries are not enabled in this phase.",
            )
        if self.limits.max_output_tokens < 16:
            return _refusal(
                "provider_token_limit_too_small",
                "The live provider token ceiling is below the provider API minimum.",
                "Set max_output_tokens to at least 16.",
            )
        if self.estimated_cost_usd_per_request <= 0:
            return _refusal(
                "invalid_provider_cost_estimate",
                "estimated_cost_usd_per_request must be greater than zero.",
                "Supply a conservative per-request estimate.",
            )
        if (
            self.estimated_cost_usd_per_request
            > self.limits.max_estimated_cost_usd
        ):
            return _refusal(
                "provider_spend_limit_exceeded",
                "The per-request estimate exceeds the configured spend ceiling.",
                "Lower the estimate or raise the ceiling deliberately.",
            )
        return None


@dataclass(frozen=True)
class LiveProviderAdapter:
    """Run one synthetic scenario through one explicitly enabled provider call."""

    policy: LiveProviderPolicy
    transport: HttpTransport | None = None

    @property
    def agent_id(self) -> str:
        """Return a stable report identifier without exposing credentials."""

        return f"{self.policy.provider_id}-live"

    def run(
        self,
        request: ScenarioRequest,
        environment: object,
    ) -> AdapterRun:
        """Send one bounded synthetic request and normalize its result."""

        refusal = self.policy.validate()
        if refusal is not None:
            return AdapterRun(refusal=refusal)
        credential = os.environ.get(self.policy.credential_env_var)
        if not credential:
            return AdapterRun(
                refusal=_refusal(
                    "provider_credential_missing",
                    "The required provider credential is not present.",
                    f"Set {self.policy.credential_env_var} in the local process environment.",
                )
            )
        if credential.strip().lower() in _PLACEHOLDER_CREDENTIALS:
            return AdapterRun(
                refusal=_refusal(
                    "provider_credential_placeholder",
                    "The provider credential is still the command example placeholder.",
                    f"Replace the placeholder with the local {self.policy.credential_env_var} value; do not paste the credential into a report or chat.",
                )
            )
        if not _is_synthetic_environment(environment):
            return AdapterRun(
                refusal=_refusal(
                    "invalid_environment",
                    "The live adapter requires the local synthetic environment.",
                    "Use a built-in scenario through the local CLI.",
                )
            )
        body = _request_body(self.policy, request)
        started = time.monotonic()
        try:
            transport = self.transport or _default_transport
            response_bytes = transport(
                _ENDPOINTS[self.policy.provider_id],
                _headers(self.policy.provider_id, credential),
                body,
                self.policy.limits.max_elapsed_seconds,
            )
        except urllib.error.HTTPError as error:
            return AdapterRun(
                refusal=_http_refusal(error.code),
            )
        except (OSError, urllib.error.URLError, TimeoutError):
            return AdapterRun(
                refusal=_refusal(
                    "provider_transport_failed",
                    "The provider request did not complete.",
                    "Check the local network and provider availability; no retry was attempted.",
                )
            )
        elapsed_seconds = time.monotonic() - started
        if not isinstance(response_bytes, bytes):
            return AdapterRun(
                refusal=_refusal(
                    "provider_transport_invalid_response",
                    "The provider transport did not return bytes.",
                    "Use a bytes response and keep provider parsing inside the adapter.",
                )
            )
        if len(response_bytes) > _MAX_RESPONSE_BYTES:
            return AdapterRun(
                refusal=_refusal(
                    "provider_response_too_large",
                    "The provider response exceeded the local response-size ceiling.",
                    "Reduce the provider output before retrying.",
                )
            )
        try:
            provider_response = json.loads(response_bytes.decode("utf-8"))
            model_payload = _extract_model_payload(
                self.policy.provider_id,
                provider_response,
            )
            usage = _live_usage(
                provider_response,
                elapsed_seconds=elapsed_seconds,
                estimated_cost_usd=self.policy.estimated_cost_usd_per_request,
            )
            execution_budget = self.policy.limits.execution_budget(usage)
            refusal = self.policy.limits.check_usage(usage)
            if refusal is not None:
                return AdapterRun(
                    refusal=refusal,
                    execution_budget=execution_budget,
                )
            safe_payload = _combine_payload(
                self.policy.provider_id,
                model_payload,
                usage,
            )
            translated = translate_provider_payload(
                self.policy.provider_id,
                safe_payload,
                scenario_id=request.scenario_id,
                agent_id=self.agent_id,
            )
            return replace(translated, execution_budget=execution_budget)
        except ProviderPayloadError as error:
            return AdapterRun(
                refusal=_refusal(
                    error.error,
                    error.message,
                    error.guidance,
                )
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            return AdapterRun(
                refusal=_refusal(
                    "provider_response_refused",
                    "The provider response was not in the reviewed safe structured shape.",
                    "Use a provider response containing only the requested identifier-only event object.",
                )
            )


def live_provider_adapter(
    policy: LiveProviderPolicy,
    *,
    transport: HttpTransport | None = None,
) -> LiveProviderAdapter:
    """Construct one live adapter without reading credentials yet."""

    return LiveProviderAdapter(policy=policy, transport=transport)


def extract_provider_payload(
    provider_id: str,
    response: object,
) -> dict[str, object]:
    """Extract the reviewed structured payload without reading credentials."""

    return _extract_model_payload(provider_id, response)


def _request_body(
    policy: LiveProviderPolicy,
    request: ScenarioRequest,
) -> bytes:
    requirement_ids = tuple(
        requirement.requirement_id for requirement in request.contract.requirements
    )
    safe_request = {
        "scenario_id": request.scenario_id,
        "available_tools": list(request.available_tools),
        "requirement_ids": list(requirement_ids),
    }
    if policy.provider_id == "openai":
        payload = {
            "model": policy.model,
            "store": False,
            "instructions": _LIVE_INSTRUCTIONS,
            "input": json.dumps(safe_request, sort_keys=True),
            "max_output_tokens": policy.limits.max_output_tokens,
        }
    else:
        payload = {
            "model": policy.model,
            "max_tokens": policy.limits.max_output_tokens,
            "system": _LIVE_INSTRUCTIONS,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(safe_request, sort_keys=True),
                }
            ],
        }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _headers(provider_id: str, credential: str) -> dict[str, str]:
    if provider_id == "openai":
        return {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        }
    return {
        "x-api-key": credential,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _extract_model_payload(provider_id: str, response: object) -> dict[str, object]:
    if not isinstance(response, dict):
        raise ProviderPayloadError(
            "provider_response_refused",
            "The provider response was not an object.",
            "Use the provider's structured JSON response.",
        )
    if provider_id == "openai":
        text = _openai_output_text(response)
        payload = _json_object(text)
        if set(payload) != {"events"}:
            raise ProviderPayloadError(
                "provider_response_refused",
                "The OpenAI response did not contain exactly the safe events field.",
                "Return only an events array with identifier-only records.",
            )
        return payload
    text = _anthropic_output_text(response)
    payload = _json_object(text)
    if set(payload) != {"content"}:
        raise ProviderPayloadError(
            "provider_response_refused",
            "The Anthropic response did not contain exactly the safe content field.",
            "Return only a content array with identifier-only records.",
        )
    return payload


def _openai_output_text(response: dict[str, object]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        raise ProviderPayloadError(
            "provider_response_refused",
            "The OpenAI response did not contain an output list.",
            "Return one message containing the safe JSON object.",
        )
    texts = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            ):
                texts.append(part["text"])
    if len(texts) != 1:
        raise ProviderPayloadError(
            "provider_response_refused",
            "The OpenAI response did not contain exactly one structured output.",
            "Return exactly one output_text JSON object.",
        )
    return texts[0]


def _anthropic_output_text(response: dict[str, object]) -> str:
    content = response.get("content")
    if not isinstance(content, list):
        raise ProviderPayloadError(
            "provider_response_refused",
            "The Anthropic response did not contain a content list.",
            "Return exactly one text block containing the safe JSON object.",
        )
    texts = [
        item["text"]
        for item in content
        if (
            isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        )
    ]
    if len(texts) != 1:
        raise ProviderPayloadError(
            "provider_response_refused",
            "The Anthropic response did not contain exactly one structured output.",
            "Return exactly one text block containing the safe JSON object.",
        )
    return texts[0]


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ProviderPayloadError(
            "provider_response_refused",
            "The provider output was not valid JSON.",
            "Return the requested safe JSON object without surrounding prose.",
        ) from error
    if not isinstance(parsed, dict):
        raise ProviderPayloadError(
            "provider_response_refused",
            "The provider output was not a JSON object.",
            "Return one JSON object containing only the safe event field.",
        )
    return parsed


def _live_usage(
    response: object,
    *,
    elapsed_seconds: float,
    estimated_cost_usd: float,
) -> dict[str, int | float]:
    if not isinstance(response, dict):
        raise ProviderPayloadError(
            "provider_response_refused",
            "The provider response was not an object.",
            "Return a JSON object with usage metadata.",
        )
    raw_usage = response.get("usage")
    if not isinstance(raw_usage, dict):
        raise ProviderPayloadError(
            "provider_usage_missing",
            "The provider response did not include usage metadata.",
            "Use a response that reports output token usage.",
        )
    output_tokens = raw_usage.get("output_tokens")
    if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
        raise ProviderPayloadError(
            "provider_usage_missing",
            "The provider response did not include an integer output-token count.",
            "Use a response that reports output_tokens.",
        )
    usage = {
        "requests": 1,
        "output_tokens": output_tokens,
        "elapsed_seconds": elapsed_seconds,
        "estimated_cost_usd": estimated_cost_usd,
    }
    _parse_usage(usage)
    return usage


def _combine_payload(
    provider_id: str,
    model_payload: dict[str, object],
    usage: dict[str, int | float],
) -> dict[str, object]:
    if provider_id == "openai":
        return {"events": model_payload["events"], "usage": usage}
    return {
        "content": model_payload["content"],
        "stop_reason": "end_turn",
        "usage": usage,
    }


def _default_transport(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout_seconds: float,
) -> bytes:
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with _LIVE_OPENER.open(request, timeout=timeout_seconds) as response:
            return response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError:
        raise


def _is_synthetic_environment(environment: object) -> bool:
    """Keep the first live boundary limited to built-in synthetic scenarios."""

    return isinstance(environment, SimulatedToolEnvironment)


def _refusal(error: str, message: str, guidance: str) -> AdapterRefusal:
    return AdapterRefusal(error=error, message=message, guidance=guidance)


def _http_refusal(status_code: int) -> AdapterRefusal:
    """Map an HTTP status to a safe diagnostic without exposing response content."""

    if status_code in {401, 403}:
        return _refusal(
            "provider_authentication_failed",
            f"The provider rejected the credential or permission with HTTP {status_code}.",
            "Check that the local API key is current, belongs to the intended workspace, and has available credits.",
        )
    if status_code == 404:
        return _refusal(
            "provider_model_or_endpoint_not_found",
            "The provider did not recognise the configured model or endpoint.",
            "Check the exact API model identifier shown by the provider dashboard.",
        )
    if status_code == 429:
        return _refusal(
            "provider_rate_limited",
            "The provider rate-limited the request with HTTP 429.",
            "Wait for the provider limit window or reduce request volume; this adapter does not retry.",
        )
    if 500 <= status_code <= 599:
        return _refusal(
            "provider_service_unavailable",
            f"The provider returned a server error with HTTP {status_code}.",
            "Check provider status and rerun once the service is available; this adapter does not retry.",
        )
    return _refusal(
        "provider_request_rejected",
        f"The provider rejected the request with HTTP {status_code}.",
        "Check the model identifier and reviewed request contract; response content was discarded.",
    )
