"""Offline evidence-contract checks for tool-using AI agents."""

from .models import (
    AgentReport,
    AssuranceDimension,
    DimensionSummary,
    EvidenceContract,
    EvidenceRequirement,
    Finding,
    FindingStatus,
    Trace,
)
from .adapters import ScenarioAdapter, reference_adapters, trace_to_events
from .environment import (
    FaultInjection,
    FaultMode,
    SimulatedToolEnvironment,
    ToolObservation,
    ToolSpec,
    environment_for_scenario,
)
from .evaluators import (
    EvaluatorCase,
    EvaluatorValidityResult,
    all_evaluator_failures_caught,
    run_evaluator_validity,
)
from .protocol import (
    AdapterRefusal,
    AdapterRun,
    AgentAdapter,
    EventType,
    ObservableEvent,
    ScenarioRequest,
    validate_adapter_run,
)
from .runner import run_comparison

__all__ = [
    "AgentReport",
    "AdapterRefusal",
    "AdapterRun",
    "AgentAdapter",
    "AssuranceDimension",
    "DimensionSummary",
    "EvidenceContract",
    "EvidenceRequirement",
    "FaultInjection",
    "FaultMode",
    "EvaluatorCase",
    "EvaluatorValidityResult",
    "Finding",
    "FindingStatus",
    "EventType",
    "ObservableEvent",
    "ScenarioRequest",
    "ScenarioAdapter",
    "SimulatedToolEnvironment",
    "ToolObservation",
    "ToolSpec",
    "Trace",
    "all_evaluator_failures_caught",
    "environment_for_scenario",
    "reference_adapters",
    "run_comparison",
    "run_evaluator_validity",
    "trace_to_events",
    "validate_adapter_run",
]
