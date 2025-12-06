"""Inspection Mode Controller - YAML-driven batch network inspections.

Architecture:
    YAML Config → Controller → BatchExecutor → ReportGenerator

    1. Load YAML inspection config
    2. Resolve device scope (NetBox filter)
    3. Execute checks in parallel across devices
    4. Generate structured report with threshold violations

Usage:
    from olav.modes.inspection import InspectionModeController, run_inspection

    # From YAML config
    controller = InspectionModeController()
    result = await controller.run("config/inspections/daily_core_check.yaml")

    # Or direct query
    result = await run_inspection("巡检所有核心路由器")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from olav.modes.shared.debug import DebugContext

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


class ThresholdConfig(BaseModel):
    """Threshold configuration for inspection checks."""

    field: str  # Field name to check
    operator: Literal[">=", "<=", ">", "<", "==", "!="] = ">="
    value: Any  # Expected value
    severity: Literal["critical", "warning", "info"] = "warning"
    message: str = ""  # Custom message template


class CheckConfig(BaseModel):
    """Individual check configuration.

    Supports two modes:
    1. Intent mode (smart): Only provide 'intent', LLM compiles to parameters
    2. Explicit mode: Provide 'tool' and 'parameters' directly

    If both are provided, explicit parameters override LLM compilation.
    """

    name: str
    description: str = ""

    # Smart mode: natural language intent (LLM compiles to tool/parameters)
    intent: str | None = Field(
        default=None,
        description="Natural language intent for LLM compilation"
    )
    severity: Literal["critical", "warning", "info"] = Field(
        default="warning",
        description="Check severity level"
    )

    # Explicit mode: directly specify tool and parameters
    tool: str | None = Field(
        default=None,
        description="Tool name (suzieq_query, netbox_api, etc.)"
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    threshold: ThresholdConfig | None = None

    enabled: bool = True

    @property
    def is_intent_mode(self) -> bool:
        """Check if this is intent-based (smart) mode."""
        return self.intent is not None and self.tool is None

    @property
    def is_explicit_mode(self) -> bool:
        """Check if this is explicit parameter mode."""
        return self.tool is not None


class DeviceFilter(BaseModel):
    """Device filter for NetBox queries."""

    netbox_filter: dict[str, Any] = Field(default_factory=dict)
    explicit_devices: list[str] = Field(default_factory=list)


class InspectionConfig(BaseModel):
    """Full inspection configuration."""

    name: str
    description: str = ""
    devices: DeviceFilter = Field(default_factory=DeviceFilter)
    checks: list[CheckConfig] = Field(default_factory=list)

    # Optional scheduling (for future cron integration)
    schedule: str | None = None  # Cron expression
    timeout_seconds: int = 300


@dataclass
class CheckResult:
    """Result of a single check on a device."""

    device: str
    check_name: str
    success: bool
    actual_value: Any = None
    threshold_violated: bool = False
    severity: str = "info"
    message: str = ""
    raw_output: Any = None
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class InspectionResult:
    """Result of a full inspection run."""

    config_name: str
    started_at: str
    completed_at: str

    # Device summary
    total_devices: int = 0
    devices_passed: int = 0
    devices_failed: int = 0

    # Check summary
    total_checks: int = 0
    checks_passed: int = 0
    checks_failed: int = 0

    # Detailed results
    check_results: list[CheckResult] = field(default_factory=list)

    # Violations grouped by severity
    critical_violations: list[CheckResult] = field(default_factory=list)
    warning_violations: list[CheckResult] = field(default_factory=list)

    # Debug
    debug_output: Any | None = None

    @property
    def duration_seconds(self) -> float:
        """Calculate total duration."""
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.completed_at)
        return (end - start).total_seconds()

    @property
    def has_critical(self) -> bool:
        """Check if any critical violations exist."""
        return len(self.critical_violations) > 0

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# 📋 Inspection Report: {self.config_name}\n",
            f"**Started**: {self.started_at}",
            f"**Duration**: {self.duration_seconds:.1f}s",
            "",
            "## Summary\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Devices | {self.devices_passed}/{self.total_devices} passed |",
            f"| Checks | {self.checks_passed}/{self.total_checks} passed |",
            f"| Critical | {len(self.critical_violations)} |",
            f"| Warnings | {len(self.warning_violations)} |",
            "",
        ]

        if self.critical_violations:
            lines.extend([
                "## 🔴 Critical Violations\n",
            ])
            for v in self.critical_violations:
                lines.append(f"- **{v.device}** / {v.check_name}: {v.message}")
            lines.append("")

        if self.warning_violations:
            lines.extend([
                "## 🟡 Warnings\n",
            ])
            for v in self.warning_violations:
                lines.append(f"- **{v.device}** / {v.check_name}: {v.message}")
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# Inspection Controller
# =============================================================================


class InspectionModeController:
    """Controller for YAML-driven batch inspections.

    The controller:
    1. Loads and validates YAML config
    2. Resolves device scope via NetBox
    3. Executes checks in parallel
    4. Aggregates results and generates report

    Usage:
        controller = InspectionModeController()
        result = await controller.run("config/inspections/daily_core_check.yaml")
    """

    def __init__(
        self,
        max_parallel_devices: int = 10,
        timeout_seconds: int = 300,
    ) -> None:
        """Initialize controller.

        Args:
            max_parallel_devices: Max devices to check in parallel.
            timeout_seconds: Global timeout for inspection.
        """
        self.max_parallel_devices = max_parallel_devices
        self.timeout_seconds = timeout_seconds

    def load_config(self, config_path: str | Path) -> InspectionConfig:
        """Load and parse YAML config.

        Args:
            config_path: Path to YAML config file.

        Returns:
            Parsed InspectionConfig.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If config is invalid.
        """
        path = Path(config_path)
        if not path.exists():
            msg = f"Config not found: {path}"
            raise FileNotFoundError(msg)

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            msg = f"Empty config: {path}"
            raise ValueError(msg)

        # Parse checks - handle threshold as nested dict
        checks = []
        for check_data in raw.get("checks", []):
            if "threshold" in check_data and isinstance(check_data["threshold"], dict):
                check_data["threshold"] = ThresholdConfig(**check_data["threshold"])
            checks.append(CheckConfig(**check_data))

        raw["checks"] = checks

        # Parse devices filter
        if "devices" in raw:
            raw["devices"] = DeviceFilter(**raw["devices"])

        return InspectionConfig(**raw)

    async def resolve_devices(self, device_filter: DeviceFilter) -> list[str]:
        """Resolve device list from filter.

        Args:
            device_filter: Device filter configuration.

        Returns:
            List of device hostnames.
        """
        # Explicit devices take priority
        if device_filter.explicit_devices:
            return device_filter.explicit_devices

        # Query NetBox if filter provided
        if device_filter.netbox_filter:
            try:
                from olav.tools.netbox_tool import NetBoxAPITool

                netbox = NetBoxAPITool()
                result = await netbox.execute(
                    path="/api/dcim/devices/",
                    method="GET",
                    params={
                        **device_filter.netbox_filter,
                        "limit": 100,
                    },
                )

                if not result.error and result.data:
                    return [d["name"] for d in result.data if isinstance(d, dict) and "name" in d]
            except Exception as e:
                logger.warning(f"Failed to query NetBox: {e}")

        return []

    async def compile_check(self, check: CheckConfig) -> tuple[str, dict[str, Any], ThresholdConfig | None]:
        """Compile check to tool/parameters using IntentCompiler if needed.

        Args:
            check: Check configuration.

        Returns:
            Tuple of (tool_name, parameters, threshold_config).
        """
        # Explicit mode: use provided tool/parameters directly
        if check.is_explicit_mode:
            return check.tool or "suzieq_query", check.parameters, check.threshold

        # Intent mode: use IntentCompiler
        if check.is_intent_mode and check.intent:
            from olav.modes.inspection.compiler import IntentCompiler

            compiler = IntentCompiler()
            plan = await compiler.compile(
                intent=check.intent,
                check_name=check.name,
                severity=check.severity,
            )

            # Build parameters from compiled plan
            parameters = {
                "table": plan.table,
                "method": plan.method,
                **plan.filters,
            }
            if plan.columns:
                parameters["columns"] = plan.columns

            # Build threshold from validation rule
            threshold = None
            if plan.validation:
                threshold = ThresholdConfig(
                    field=plan.validation.field,
                    operator=plan.validation.operator,  # type: ignore
                    value=plan.validation.expected,
                    severity=check.severity,
                    message=f"{{device}}: {plan.validation.field} 不满足条件 {plan.validation.operator} {plan.validation.expected}",
                )

            return "suzieq_query", parameters, threshold

        # Fallback: use description as intent
        if check.description:
            from olav.modes.inspection.compiler import IntentCompiler

            compiler = IntentCompiler()
            plan = await compiler.compile(
                intent=check.description,
                check_name=check.name,
                severity=check.severity,
            )

            parameters = {
                "table": plan.table,
                "method": plan.method,
                **plan.filters,
            }

            threshold = None
            if plan.validation:
                threshold = ThresholdConfig(
                    field=plan.validation.field,
                    operator=plan.validation.operator,  # type: ignore
                    value=plan.validation.expected,
                    severity=check.severity,
                    message=f"{{device}}: {plan.validation.field} 不满足条件",
                )

            return "suzieq_query", parameters, threshold

        # No intent or tool specified - error
        msg = f"Check '{check.name}' must have either 'intent' or 'tool' specified"
        raise ValueError(msg)

    async def execute_check(
        self,
        device: str,
        check: CheckConfig,
    ) -> CheckResult:
        """Execute a single check on a device.

        Supports both intent mode (LLM compilation) and explicit mode.

        Args:
            device: Device hostname.
            check: Check configuration.

        Returns:
            CheckResult with findings.
        """
        import time

        start = time.perf_counter()

        try:
            # Compile check to tool/parameters
            tool_name, parameters, threshold = await self.compile_check(check)

            # Execute tool
            if tool_name == "suzieq_query":
                from olav.tools.suzieq_tool import SuzieQTool

                tool = SuzieQTool()
                params = {
                    **parameters,
                    "hostname": device,
                }
                result = await tool.execute(**params)
                # SuzieQTool returns ToolOutput, extract data
                if hasattr(result, "data"):
                    result = result.data
            else:
                # Unknown tool
                return CheckResult(
                    device=device,
                    check_name=check.name,
                    success=False,
                    error=f"Unknown tool: {tool_name}",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )

            duration = (time.perf_counter() - start) * 1000

            # Check threshold if configured
            threshold_violated = False
            severity = check.severity
            message = ""
            actual_value = result

            if threshold:
                # Extract value from result
                if isinstance(result, dict):
                    actual_value = result.get(threshold.field, result)
                elif isinstance(result, list):
                    actual_value = len(result)

                # Evaluate threshold
                threshold_violated = not self._evaluate_threshold(
                    actual_value,
                    threshold.operator,
                    threshold.value,
                )

                if threshold_violated:
                    severity = threshold.severity
                    message = threshold.message.format(
                        device=device,
                        actual=actual_value,
                        value=threshold.value,
                    ) if threshold.message else f"{device}: {threshold.field} = {actual_value}"

            return CheckResult(
                device=device,
                check_name=check.name,
                success=not threshold_violated,
                actual_value=actual_value,
                threshold_violated=threshold_violated,
                severity=severity,
                message=message,
                raw_output=result,
                duration_ms=duration,
            )

        except Exception as e:
            return CheckResult(
                device=device,
                check_name=check.name,
                success=False,
                error=str(e),
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    def _evaluate_threshold(
        self,
        actual: Any,
        operator: str,
        expected: Any,
    ) -> bool:
        """Evaluate threshold condition.

        Args:
            actual: Actual value from check.
            operator: Comparison operator.
            expected: Expected threshold value.

        Returns:
            True if threshold is satisfied.
        """
        try:
            if operator == ">=":
                return actual >= expected
            if operator == "<=":
                return actual <= expected
            if operator == ">":
                return actual > expected
            if operator == "<":
                return actual < expected
            if operator == "==":
                return actual == expected
            if operator == "!=":
                return actual != expected
            return True  # Unknown operator, assume pass
        except Exception:
            return False

    async def run(
        self,
        config_path: str | Path,
        debug_context: DebugContext | None = None,
    ) -> InspectionResult:
        """Run inspection from YAML config.

        Args:
            config_path: Path to YAML config.
            debug_context: Optional debug context.

        Returns:
            InspectionResult with all findings.
        """
        started_at = datetime.now().isoformat()

        # Load config
        config = self.load_config(config_path)

        logger.info(f"Starting inspection: {config.name}")

        if debug_context:
            debug_context.log_graph_state(
                node="inspection.load_config",
                state={
                    "config_name": config.name,
                    "checks_count": len(config.checks),
                },
            )

        # Resolve devices
        devices = await self.resolve_devices(config.devices)

        if not devices:
            logger.warning("No devices found for inspection")
            return InspectionResult(
                config_name=config.name,
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
                total_devices=0,
            )

        logger.info(f"Inspecting {len(devices)} devices")

        # Execute checks in parallel
        enabled_checks = [c for c in config.checks if c.enabled]
        all_results: list[CheckResult] = []

        # Semaphore for parallel execution limit
        semaphore = asyncio.Semaphore(self.max_parallel_devices)

        async def check_device(device: str) -> list[CheckResult]:
            async with semaphore:
                results = []
                for check in enabled_checks:
                    result = await self.execute_check(device, check)
                    results.append(result)
                return results

        # Run all devices in parallel
        tasks = [check_device(device) for device in devices]
        device_results = await asyncio.gather(*tasks, return_exceptions=True)

        for dr in device_results:
            if isinstance(dr, list):
                all_results.extend(dr)
            elif isinstance(dr, Exception):
                logger.error(f"Device check failed: {dr}")

        # Aggregate results
        check_results = all_results
        checks_passed = sum(1 for r in check_results if r.success)

        # Group violations by severity
        critical_violations = [r for r in check_results if r.severity == "critical" and r.threshold_violated]
        warning_violations = [r for r in check_results if r.severity == "warning" and r.threshold_violated]

        # Count devices
        failed_devices = set()
        for r in check_results:
            if not r.success:
                failed_devices.add(r.device)

        completed_at = datetime.now().isoformat()

        if debug_context:
            debug_context.log_graph_state(
                node="inspection.complete",
                state={
                    "total_checks": len(check_results),
                    "checks_passed": checks_passed,
                    "critical_count": len(critical_violations),
                },
            )

        return InspectionResult(
            config_name=config.name,
            started_at=started_at,
            completed_at=completed_at,
            total_devices=len(devices),
            devices_passed=len(devices) - len(failed_devices),
            devices_failed=len(failed_devices),
            total_checks=len(check_results),
            checks_passed=checks_passed,
            checks_failed=len(check_results) - checks_passed,
            check_results=check_results,
            critical_violations=critical_violations,
            warning_violations=warning_violations,
            debug_output=debug_context.output if debug_context else None,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


async def run_inspection(
    config_path: str | Path,
    debug: bool = False,
    max_parallel: int = 10,
) -> InspectionResult:
    """Run inspection from YAML config.

    Convenience function for running inspection without class instantiation.

    Args:
        config_path: Path to YAML config.
        debug: Whether to enable debug mode.
        max_parallel: Max parallel device checks.

    Returns:
        InspectionResult with findings.

    Example:
        result = await run_inspection("config/inspections/daily_core_check.yaml")
        print(result.to_markdown())
    """
    controller = InspectionModeController(max_parallel_devices=max_parallel)

    if debug:
        async with DebugContext(enabled=True) as ctx:
            return await controller.run(config_path, ctx)
    else:
        return await controller.run(config_path)
