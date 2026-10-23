"""Subprocess adapter safety boundary and strict JSONL protocol handling.

Design rules:

1. The child command is passed as an argument vector with ``shell=False``.
2. The child receives a minimal environment and synthetic request metadata only.
3. stdout is a one-response protocol channel; stderr is diagnostics and never enters the
   report.
4. The child runs in a separate process group with bounded output and best-effort Unix
   resource limits.
5. Decode and validation failures become structured refusals instead of exceptions.
"""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    EvidenceContract,
    EvidenceRequirement,
    ToolCall,
    Trace,
)
from .protocol import (
    AdapterRefusal,
    AdapterRun,
    EventType,
    ObservableEvent,
    ScenarioRequest,
    validate_adapter_run,
)


# MODELLING ASSUMPTION: five seconds is a local-development ceiling, not a measured
# production latency target. Expose it so a measured adapter can replace the default.
DEFAULT_ADAPTER_TIMEOUT_SECONDS = 5.0
# MODELLING ASSUMPTION: 256 KiB is enough for identifier-only traces while rejecting
# accidental payload dumps. Increase only after measuring a real protocol need.
DEFAULT_MAX_RESPONSE_BYTES = 262_144
# MODELLING ASSUMPTION: diagnostics are not part of the response protocol. Keep a
# bounded pipe so an adapter cannot fill memory with stderr while stdout is valid.
DEFAULT_MAX_STDERR_BYTES = 65_536
# MODELLING ASSUMPTION: this is a local safety ceiling, not a production sizing target.
# The caller can lower it for a constrained conformance run.
DEFAULT_MAX_MEMORY_BYTES = 512 * 1024 * 1024


class ProtocolDecodeError(ValueError):
    """Raised internally when a JSONL message violates the public protocol."""


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolDecodeError(f"{context} must be an object.")
    return value


def _keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ProtocolDecodeError(f"{context} contains unknown fields.")


def _string(value: object, context: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise ProtocolDecodeError(f"{context} must be a string.")
    return value


def _number(
    value: object,
    context: str,
    *,
    allow_none: bool = False,
) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolDecodeError(f"{context} must be a number.")
    if value < 0:
        raise ProtocolDecodeError(f"{context} must be non-negative.")
    return float(value)


def _integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProtocolDecodeError(f"{context} must be a non-negative integer.")
    return value


def _integer_or_none(value: object, context: str) -> int | None:
    if value is None:
        return None
    return _integer(value, context)


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProtocolDecodeError(f"{context} must be a list of strings.")
    return tuple(value)


def scenario_request_to_dict(request: ScenarioRequest) -> dict[str, object]:
    """Serialize a request without raw task or tool payloads."""

    return {
        "scenario_id": request.scenario_id,
        "task_label": request.task_label,
        "available_tools": list(request.available_tools),
        "contract": request.contract.to_dict(),
    }


def scenario_request_from_dict(value: object) -> ScenarioRequest:
    """Decode and strictly validate one adapter request."""

    data = _object(value, "request")
    _keys(data, {"scenario_id", "task_label", "available_tools", "contract"}, "request")
    contract_data = _object(data.get("contract"), "request.contract")
    _keys(contract_data, {"scenario_id", "requirements"}, "request.contract")
    requirement_values = contract_data.get("requirements")
    if not isinstance(requirement_values, list):
        raise ProtocolDecodeError("request.contract.requirements must be a list.")
    requirements = []
    for index, requirement_value in enumerate(requirement_values):
        requirement_data = _object(
            requirement_value,
            f"request.contract.requirements[{index}]",
        )
        _keys(
            requirement_data,
            {
                "requirement_id",
                "description",
                "evidence_type",
                "source",
                "max_age_seconds",
            },
            f"request.contract.requirements[{index}]",
        )
        requirements.append(
            EvidenceRequirement(
                requirement_id=_string(
                    requirement_data.get("requirement_id"),
                    "requirement_id",
                )
                or "",
                description=_string(
                    requirement_data.get("description"),
                    "description",
                )
                or "",
                evidence_type=_string(
                    requirement_data.get("evidence_type"),
                    "evidence_type",
                )
                or "",
                source=_string(
                    requirement_data.get("source"),
                    "requirement source",
                    allow_none=True,
                ),
                max_age_seconds=_number(
                    requirement_data.get("max_age_seconds"),
                    "requirement max_age_seconds",
                    allow_none=True,
                ),
            )
        )
    return ScenarioRequest(
        scenario_id=_string(data.get("scenario_id"), "request.scenario_id") or "",
        task_label=_string(data.get("task_label"), "request.task_label") or "",
        available_tools=_string_tuple(
            data.get("available_tools"),
            "request.available_tools",
        ),
        contract=EvidenceContract(
            scenario_id=_string(
                contract_data.get("scenario_id"),
                "request.contract.scenario_id",
            )
            or "",
            requirements=tuple(requirements),
        ),
    )


def _event_from_dict(value: object, index: int) -> ObservableEvent:
    data = _object(value, f"response.events[{index}]")
    _keys(
        data,
        {"sequence", "event_id", "event_type", "name", "status", "evidence_id"},
        f"response.events[{index}]",
    )
    try:
        event_type = EventType(
            _string(data.get("event_type"), "event_type") or ""
        )
    except ValueError as error:
        raise ProtocolDecodeError("response event_type is not recognised.") from error
    sequence = data.get("sequence")
    if not isinstance(sequence, int):
        raise ProtocolDecodeError("response event sequence must be an integer.")
    return ObservableEvent(
        sequence=sequence,
        event_id=_string(data.get("event_id"), "event_id") or "",
        event_type=event_type,
        name=_string(data.get("name"), "event name") or "",
        status=_string(data.get("status"), "event status", allow_none=True),
        evidence_id=_string(
            data.get("evidence_id"),
            "event evidence_id",
            allow_none=True,
        ),
    )


def _trace_from_dict(value: object) -> Trace:
    data = _object(value, "response.trace")
    _keys(
        data,
        {
            "scenario_id",
            "agent_id",
            "workflow_id",
            "transport_status",
            "semantic_outcome",
            "retry_count",
            "estimated_cost_usd",
            "max_retries",
            "max_estimated_cost_usd",
            "tool_calls",
            "claim",
            "answer",
            "abstained",
            "abstention_reasons",
            "evidence_ids",
            "side_effects",
            "authorization_ids",
            "authorization_operation_ids",
            "authorization_action_digests",
            "tool_output_flags",
            "operation_ids",
            "idempotency_keys",
            "action_digests",
            "reconciliation_ids",
            "reconciliation_statuses",
            "policy_version",
            "policy_digest",
            "authorization_scopes",
            "escalation_status",
            "escalation_id",
        },
        "response.trace",
    )
    tool_call_values = data.get("tool_calls")
    if not isinstance(tool_call_values, list):
        raise ProtocolDecodeError("response.trace.tool_calls must be a list.")
    tool_calls = []
    for index, tool_call_value in enumerate(tool_call_values):
        tool_call_data = _object(
            tool_call_value,
            f"response.trace.tool_calls[{index}]",
        )
        _keys(
            tool_call_data,
            {"name", "result_status", "result_id", "source", "age_seconds"},
            f"response.trace.tool_calls[{index}]",
        )
        tool_calls.append(
            ToolCall(
                name=_string(tool_call_data.get("name"), "tool name") or "",
                arguments={},
                result_status=_string(
                    tool_call_data.get("result_status"),
                    "tool result status",
                )
                or "",
                result_id=_string(
                    tool_call_data.get("result_id"),
                    "tool result id",
                    allow_none=True,
                ),
                source=_string(
                    tool_call_data.get("source"),
                    "tool evidence source",
                    allow_none=True,
                ),
                age_seconds=_number(
                    tool_call_data.get("age_seconds"),
                    "tool evidence age_seconds",
                    allow_none=True,
                ),
            )
        )
    abstained = data.get("abstained")
    if not isinstance(abstained, bool):
        raise ProtocolDecodeError("response.trace.abstained must be a boolean.")
    return Trace(
        scenario_id=_string(data.get("scenario_id"), "trace scenario_id") or "",
        agent_id=_string(data.get("agent_id"), "trace agent_id") or "",
        workflow_id=_string(
            data.get("workflow_id"),
            "trace workflow_id",
            allow_none=True,
        ),
        transport_status=_string(
            data.get("transport_status"),
            "trace transport_status",
            allow_none=True,
        ),
        semantic_outcome=_string(
            data.get("semantic_outcome"),
            "trace semantic_outcome",
            allow_none=True,
        ),
        retry_count=_integer(data.get("retry_count", 0), "trace retry_count"),
        estimated_cost_usd=_number(
            data.get("estimated_cost_usd"),
            "trace estimated_cost_usd",
            allow_none=True,
        ),
        max_retries=_integer_or_none(
            data.get("max_retries"),
            "trace max_retries",
        ),
        max_estimated_cost_usd=_number(
            data.get("max_estimated_cost_usd"),
            "trace max_estimated_cost_usd",
            allow_none=True,
        ),
        tool_calls=tuple(tool_calls),
        claim=_string(data.get("claim"), "trace claim", allow_none=True),
        answer=_string(data.get("answer"), "trace answer", allow_none=True),
        abstained=abstained,
        abstention_reasons=_string_tuple(
            data.get("abstention_reasons", []),
            "trace abstention_reasons",
        ),
        evidence_ids=_string_tuple(data.get("evidence_ids"), "trace evidence_ids"),
        side_effects=_string_tuple(data.get("side_effects"), "trace side_effects"),
        authorization_ids=_string_tuple(
            data.get("authorization_ids"),
            "trace authorization_ids",
        ),
        authorization_operation_ids=_string_tuple(
            data.get("authorization_operation_ids", []),
            "trace authorization_operation_ids",
        ),
        authorization_action_digests=_string_tuple(
            data.get("authorization_action_digests", []),
            "trace authorization_action_digests",
        ),
        tool_output_flags=_string_tuple(
            data.get("tool_output_flags"),
            "trace tool_output_flags",
        ),
        operation_ids=_string_tuple(
            data.get("operation_ids", []),
            "trace operation_ids",
        ),
        idempotency_keys=_string_tuple(
            data.get("idempotency_keys", []),
            "trace idempotency_keys",
        ),
        action_digests=_string_tuple(
            data.get("action_digests", []),
            "trace action_digests",
        ),
        reconciliation_ids=_string_tuple(
            data.get("reconciliation_ids", []),
            "trace reconciliation_ids",
        ),
        reconciliation_statuses=_string_tuple(
            data.get("reconciliation_statuses", []),
            "trace reconciliation_statuses",
        ),
        policy_version=_string(
            data.get("policy_version"),
            "trace policy_version",
            allow_none=True,
        ),
        policy_digest=_string(
            data.get("policy_digest"),
            "trace policy_digest",
            allow_none=True,
        ),
        authorization_scopes=_string_tuple(
            data.get("authorization_scopes", []),
            "trace authorization_scopes",
        ),
        escalation_status=_string(
            data.get("escalation_status"),
            "trace escalation_status",
            allow_none=True,
        ),
        escalation_id=_string(
            data.get("escalation_id"),
            "trace escalation_id",
            allow_none=True,
        ),
    )


def adapter_run_to_dict(run: AdapterRun) -> dict[str, object]:
    """Serialize an adapter result using the strict public response shape."""

    response: dict[str, object] = {}
    if run.trace is not None:
        response["trace"] = {
            "scenario_id": run.trace.scenario_id,
            "agent_id": run.trace.agent_id,
            "workflow_id": run.trace.workflow_id,
            "transport_status": run.trace.transport_status,
            "semantic_outcome": run.trace.semantic_outcome,
            "retry_count": run.trace.retry_count,
            "estimated_cost_usd": run.trace.estimated_cost_usd,
            "max_retries": run.trace.max_retries,
            "max_estimated_cost_usd": run.trace.max_estimated_cost_usd,
            "tool_calls": [
                {
                    "name": call.name,
                    "result_status": call.result_status,
                    "result_id": call.result_id,
                    **(
                        {"source": call.source}
                        if call.source is not None
                        else {}
                    ),
                    **(
                        {"age_seconds": call.age_seconds}
                        if call.age_seconds is not None
                        else {}
                    ),
                }
                for call in run.trace.tool_calls
            ],
            "claim": run.trace.claim,
            "answer": run.trace.answer,
            "abstained": run.trace.abstained,
            "abstention_reasons": list(run.trace.abstention_reasons),
            "evidence_ids": list(run.trace.evidence_ids),
            "side_effects": list(run.trace.side_effects),
            "authorization_ids": list(run.trace.authorization_ids),
            "authorization_operation_ids": list(
                run.trace.authorization_operation_ids
            ),
            "authorization_action_digests": list(
                run.trace.authorization_action_digests
            ),
            "tool_output_flags": list(run.trace.tool_output_flags),
            "operation_ids": list(run.trace.operation_ids),
            "idempotency_keys": list(run.trace.idempotency_keys),
            "action_digests": list(run.trace.action_digests),
            "reconciliation_ids": list(run.trace.reconciliation_ids),
            "reconciliation_statuses": list(run.trace.reconciliation_statuses),
            "policy_version": run.trace.policy_version,
            "policy_digest": run.trace.policy_digest,
            "authorization_scopes": list(run.trace.authorization_scopes),
            "escalation_status": run.trace.escalation_status,
            "escalation_id": run.trace.escalation_id,
        }
    if run.refusal is not None:
        response["refusal"] = run.refusal.to_dict()
    if run.trace is not None:
        response["events"] = [event.to_dict() for event in run.events]
    return response


def adapter_run_from_dict(value: object) -> AdapterRun:
    """Decode and strictly validate one adapter response."""

    data = _object(value, "response")
    _keys(data, {"trace", "events", "refusal"}, "response")
    trace_value = data.get("trace")
    refusal_value = data.get("refusal")
    trace = _trace_from_dict(trace_value) if trace_value is not None else None
    refusal = None
    if refusal_value is not None:
        refusal_data = _object(refusal_value, "response.refusal")
        _keys(
            refusal_data,
            {"error", "message", "guidance"},
            "response.refusal",
        )
        refusal = AdapterRefusal(
            error=_string(refusal_data.get("error"), "refusal error") or "",
            message=_string(refusal_data.get("message"), "refusal message") or "",
            guidance=_string(refusal_data.get("guidance"), "refusal guidance") or "",
        )
    event_values = data.get("events", [])
    if not isinstance(event_values, list):
        raise ProtocolDecodeError("response.events must be a list.")
    events = tuple(_event_from_dict(value, index) for index, value in enumerate(event_values))
    run = AdapterRun(trace=trace, refusal=refusal, events=events)
    protocol_refusal = validate_adapter_run(run)
    if protocol_refusal is not None:
        raise ProtocolDecodeError(protocol_refusal.message)
    return run


def _safe_environment() -> dict[str, str]:
    """Return only environment values needed to locate the supplied command."""

    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONUNBUFFERED": "1",
    }


def _process_group_options(
    *,
    timeout_seconds: float,
    max_memory_bytes: int,
) -> dict[str, Any]:
    """Return platform-specific process-group and best-effort resource controls."""

    if os.name == "posix":
        options: dict[str, Any] = {"start_new_session": True}
        try:
            import resource
        except ImportError:
            return options

        def limit_resources() -> None:
            try:
                cpu_seconds = max(1, int(timeout_seconds) + 1)
                resource.setrlimit(
                    resource.RLIMIT_CPU,
                    (cpu_seconds, cpu_seconds),
                )
                resource.setrlimit(
                    resource.RLIMIT_AS,
                    (max_memory_bytes, max_memory_bytes),
                )
            except (OSError, ValueError):
                # The parent still has the wall-clock and output ceilings.
                pass

        options["preexec_fn"] = limit_resources
        return options
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return {"creationflags": creation_flags}


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Terminate the whole adapter process group where the platform supports it."""

    try:
        if os.name == "posix":
            # start_new_session=True makes the adapter PID its process-group ID.
            # Killing the group also stops descendants that inherited the protocol pipes.
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except (OSError, ProcessLookupError):
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _collect_output(
    process: subprocess.Popen[bytes],
    input_bytes: bytes,
    *,
    timeout_seconds: float,
    max_response_bytes: int,
    max_stderr_bytes: int,
) -> tuple[bytes, int] | AdapterRefusal:
    """Collect output without allowing either pipe to exceed its configured cap."""

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    try:
        process.stdin.write(input_bytes)
        process.stdin.close()
    except OSError:
        _terminate(process)
        return AdapterRefusal(
            error="adapter_stdin_failed",
            message="The adapter closed stdin before receiving the request.",
            guidance="Read one complete JSONL request from stdin before exiting.",
        )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    stdout = bytearray()
    stderr_size = 0
    started = time.monotonic()
    try:
        while selector.get_map():
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                _terminate(process)
                return AdapterRefusal(
                    error="adapter_timeout",
                    message="The adapter exceeded the configured timeout.",
                    guidance="Fix the adapter or increase the timeout only after measuring why it needs more time.",
                )
            selected = selector.select(remaining)
            if not selected:
                _terminate(process)
                return AdapterRefusal(
                    error="adapter_timeout",
                    message="The adapter exceeded the configured timeout.",
                    guidance="Fix the adapter or increase the timeout only after measuring why it needs more time.",
                )
            for key, _ in selected:
                stream = key.fileobj
                chunk = stream.read1(4096)
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if key.data == "stdout":
                    stdout.extend(chunk)
                    if len(stdout) > max_response_bytes:
                        _terminate(process)
                        return AdapterRefusal(
                            error="response_too_large",
                            message="The adapter response exceeded the configured size limit.",
                            guidance="Return only the identifier-only adapter response, not raw payloads.",
                        )
                else:
                    stderr_size += len(chunk)
                    if stderr_size > max_stderr_bytes:
                        _terminate(process)
                        return AdapterRefusal(
                            error="diagnostics_too_large",
                            message="The adapter diagnostics exceeded the configured size limit.",
                            guidance="Keep diagnostics concise and emit only the protocol response on stdout.",
                        )
        return bytes(stdout), process.wait()
    finally:
        selector.close()


@dataclass(frozen=True)
class SubprocessAdapter:
    """Run a local adapter command through the JSONL protocol."""

    agent_id: str
    command: tuple[str, ...]
    timeout_seconds: float = DEFAULT_ADAPTER_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES
    working_directory: Path | None = None

    def run(
        self,
        request: ScenarioRequest,
        environment: object,
    ) -> AdapterRun:
        """Send one request to a fresh child process and validate its response."""

        del environment
        if not self.command:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="empty_adapter_command",
                    message="No adapter command was supplied.",
                    guidance="Supply an executable and its arguments as a command vector.",
                )
            )
        if self.timeout_seconds <= 0:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="invalid_timeout",
                    message="The adapter timeout must be greater than zero.",
                    guidance="Set a positive timeout based on a measured local run.",
                )
            )
        if self.max_response_bytes <= 0:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="invalid_response_limit",
                    message="The adapter response limit must be greater than zero.",
                    guidance="Set a positive response limit for the identifier-only protocol.",
                )
            )
        if self.max_stderr_bytes <= 0:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="invalid_stderr_limit",
                    message="The adapter diagnostics limit must be greater than zero.",
                    guidance="Set a positive stderr limit for the local process boundary.",
                )
            )
        if self.max_memory_bytes <= 0:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="invalid_memory_limit",
                    message="The adapter memory limit must be greater than zero.",
                    guidance="Set a positive memory limit for the local process boundary.",
                )
            )
        if self.working_directory is not None:
            try:
                valid_working_directory = self.working_directory.is_dir()
            except OSError:
                valid_working_directory = False
            if not valid_working_directory:
                return AdapterRun(
                    refusal=AdapterRefusal(
                        error="invalid_working_directory",
                        message="The adapter working directory is not a readable directory.",
                        guidance="Provide an existing local directory for the adapter process.",
                    )
                )
        try:
            launch_options: dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "env": _safe_environment(),
                "shell": False,
                "cwd": self.working_directory,
            }
            launch_options.update(_process_group_options(
                timeout_seconds=self.timeout_seconds,
                max_memory_bytes=self.max_memory_bytes,
            ))
            process = subprocess.Popen(list(self.command), **launch_options)
        except OSError:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="adapter_launch_failed",
                    message="The adapter command could not be started.",
                    guidance="Check the executable path and command arguments.",
                )
            )
        collected = _collect_output(
            process,
            (
                json.dumps(
                    scenario_request_to_dict(request),
                    sort_keys=True,
                )
                + "\n"
            ).encode(),
            timeout_seconds=self.timeout_seconds,
            max_response_bytes=self.max_response_bytes,
            max_stderr_bytes=self.max_stderr_bytes,
        )
        if isinstance(collected, AdapterRefusal):
            return AdapterRun(refusal=collected)
        stdout, return_code = collected
        if return_code != 0:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="adapter_exit_failed",
                    message="The adapter exited with a non-zero status.",
                    guidance="Fix the adapter process and return one valid response line.",
                )
            )
        try:
            decoded = stdout.decode("utf-8")
        except UnicodeDecodeError:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="response_not_utf8",
                    message="The adapter response was not valid UTF-8.",
                    guidance="Emit one UTF-8 JSON response line on stdout.",
                )
            )
        lines = decoded.splitlines()
        if len(lines) != 1 or not lines[0].strip():
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="invalid_jsonl_response",
                    message="The adapter must emit exactly one non-empty JSONL response line.",
                    guidance="Keep diagnostics on stderr and emit one response object on stdout.",
                )
            )
        try:
            run = adapter_run_from_dict(json.loads(lines[0]))
        except (json.JSONDecodeError, ProtocolDecodeError):
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="malformed_adapter_response",
                    message="The adapter response did not match the identifier-only protocol.",
                    guidance="Use the documented response schema and remove unknown or payload fields.",
                )
            )
        if run.trace is not None:
            if run.trace.agent_id != self.agent_id:
                return AdapterRun(
                    refusal=AdapterRefusal(
                        error="agent_id_mismatch",
                        message="The adapter trace agent_id does not match the configured adapter.",
                        guidance="Set the trace agent_id to the adapter's configured identifier.",
                    )
                )
            if run.trace.scenario_id != request.scenario_id:
                return AdapterRun(
                    refusal=AdapterRefusal(
                        error="scenario_id_mismatch",
                        message="The adapter trace scenario_id does not match the request.",
                        guidance="Return a trace for the scenario in the request.",
                    )
                )
        return run
