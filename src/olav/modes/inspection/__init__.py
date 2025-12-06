"""Inspection Mode - YAML-driven batch network inspections.

Architecture:
    YAML Config → IntentCompiler (LLM) → Controller → BatchExecutor → ReportGenerator

Components:
    - InspectionModeController: Orchestrates YAML-driven inspections
    - IntentCompiler: LLM-driven intent to query plan compilation
    - InspectionConfig: Pydantic models for YAML config
    - CheckResult/InspectionResult: Result data classes

Capabilities:
    - Smart mode: Natural language intent → LLM compiles to query
    - Explicit mode: Direct tool/parameters specification
    - Query plan caching (avoid redundant LLM calls)
    - NetBox device scope resolution
    - Parallel batch execution
    - Threshold-based validation
    - Markdown report generation

Usage:
    from olav.modes.inspection import InspectionModeController, run_inspection

    # From YAML config (supports both intent and explicit mode)
    result = await run_inspection("config/inspections/daily_core_check.yaml")
    print(result.to_markdown())
"""

from olav.modes.inspection.compiler import (
    IntentCompiler,
    QueryPlan,
    ValidationRule,
)
from olav.modes.inspection.controller import (
    CheckConfig,
    CheckResult,
    DeviceFilter,
    InspectionConfig,
    InspectionModeController,
    InspectionResult,
    ThresholdConfig,
    run_inspection,
)

__all__ = [
    "CheckConfig",
    "CheckResult",
    "DeviceFilter",
    "InspectionConfig",
    # Controller
    "InspectionModeController",
    "InspectionResult",
    # Compiler
    "IntentCompiler",
    "QueryPlan",
    "ThresholdConfig",
    "ValidationRule",
    "run_inspection",
]
