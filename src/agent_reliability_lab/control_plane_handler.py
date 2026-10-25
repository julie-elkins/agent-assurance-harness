"""AWS Lambda HTTP boundary for the metadata-only assurance control plane.

The handler follows four rules:

1. Require API Gateway authentication context before reading or writing records.
2. Keep request parsing and response formatting separate from the evaluator.
3. Return structured refusals without echoing request content.
4. Treat missing configuration and missing records as failures, never as approval.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from decimal import Decimal
from typing import Any

from .control_plane import (
    ControlPlaneValidationError,
    DynamoAuditStore,
    MAX_SUBMISSION_BYTES,
    get_latest,
    submit,
)


LOGGER = logging.getLogger(__name__)
LOGGER.propagate = False
if not LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler())
LOGGER.setLevel(logging.INFO)

_STORE: DynamoAuditStore | None = None


def _json_default(value: object) -> object:
    """Convert DynamoDB numeric metadata to JSON-safe integers."""

    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_response(status_code: int, body: dict[str, object]) -> dict[str, object]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body, sort_keys=True, default=_json_default),
    }


def _refusal(
    status_code: int,
    *,
    error: str,
    guidance: str,
    details: list[str] | None = None,
) -> dict[str, object]:
    refusal: dict[str, object] = {
        "error": error,
        "message": "The hosted assurance request was refused.",
        "guidance": guidance,
    }
    if details:
        refusal["details"] = details
    return _json_response(status_code, {"refusal": refusal})


def _principal_id(event: dict[str, object]) -> str | None:
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        return None
    identity = request_context.get("identity")
    if isinstance(identity, dict):
        user_arn = identity.get("userArn")
        if isinstance(user_arn, str) and user_arn:
            return user_arn
    authorizer = request_context.get("authorizer")
    if isinstance(authorizer, dict):
        principal = authorizer.get("principalId")
        if isinstance(principal, str) and principal:
            return principal
    return None


def _request_body(event: dict[str, object]) -> object:
    body = event.get("body")
    if not isinstance(body, str):
        raise ControlPlaneValidationError(("request body must be JSON",))
    if event.get("isBase64Encoded") is True:
        try:
            body = base64.b64decode(body, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise ControlPlaneValidationError(
                ("request body must be valid UTF-8 base64 JSON",)
            ) from error
    if len(body.encode("utf-8")) > MAX_SUBMISSION_BYTES:
        raise ControlPlaneValidationError(
            (f"request body exceeds {MAX_SUBMISSION_BYTES} bytes",)
        )
    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise ControlPlaneValidationError(("request body must be valid JSON",)) from error


def _store() -> DynamoAuditStore:
    global _STORE
    if _STORE is None:
        table_name = os.environ.get("ASSURANCE_TABLE_NAME")
        if not table_name:
            raise RuntimeError("ASSURANCE_TABLE_NAME is not configured")
        _STORE = DynamoAuditStore(table_name)
    return _STORE


def lambda_handler(event: dict[str, object], context: Any) -> dict[str, object]:
    """Handle authenticated POST and GET requests from API Gateway."""

    principal_id = _principal_id(event)
    if principal_id is None:
        return _refusal(
            401,
            error="authentication_required",
            guidance="Invoke the API through an authenticated API Gateway route.",
        )

    method = str(event.get("httpMethod", "")).upper()
    path_parameters = event.get("pathParameters")
    run_id = (
        path_parameters.get("run_id")
        if isinstance(path_parameters, dict)
        else None
    )
    try:
        store = _store()
        if method == "POST" and event.get("resource") == "/reauthorizations":
            payload = _request_body(event)
            response = submit(
                payload,
                principal_id=principal_id,
                store=store,
            )
            return _json_response(200, response)
        if method == "GET" and event.get("resource") == "/runs/{run_id}":
            if not isinstance(run_id, str):
                return _refusal(
                    400,
                    error="run_id_required",
                    guidance="Provide a bounded run_id path parameter.",
                )
            record = get_latest(run_id, store=store)
            if record is None:
                return _refusal(
                    404,
                    error="run_not_found",
                    guidance="Submit the run manifest before requesting its state.",
                )
            return _json_response(200, record)
        return _refusal(
            404,
            error="route_not_found",
            guidance="Use the documented reauthorization routes.",
        )
    except ControlPlaneValidationError as error:
        return _refusal(
            400,
            error="metadata_submission_invalid",
            guidance="Send only the versioned manifest and complete revision map.",
            details=list(error.errors),
        )
    except Exception:
        LOGGER.exception("control_plane_request_failed")
        return _refusal(
            500,
            error="control_plane_unavailable",
            guidance="Retry after the service owner repairs the hosted boundary.",
        )


__all__ = ["lambda_handler"]
