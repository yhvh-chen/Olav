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
    result = await run_inspection("Inspect all core routers")
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, Field

from olav.modes.shared.debug import DebugContext

if TYPE_CHECKING:
    from olav.modes.inspection.compiler import QueryPlan

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
    """Device filter for NetBox queries.

    Priority:
    1. explicit_devices (if non-empty) → use hardcoded list
    2. netbox_filter (if non-empty) → query NetBox API
    3. Both empty → fallback to SuzieQ device table
    """

    netbox_filter: dict[str, Any] = Field(
        default_factory=dict,
        description="NetBox API filter params: tag, role, site, status, platform",
    )
    explicit_devices: list[str] = Field(
        default_factory=list,
        description="Hardcoded device list (overrides netbox_filter)",
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="Devices to exclude from netbox_filter results",
    )


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

    def to_markdown(self, verbose: bool = True) -> str:
        """Generate human-readable markdown report.

        Args:
            verbose: Include detailed check results table.
        """
        # Determine overall status
        if self.critical_violations:
            status_icon = "🔴"
            status_text = "CRITICAL"
        elif self.warning_violations:
            status_icon = "🟡"
            status_text = "WARNING"
        else:
            status_icon = "🟢"
            status_text = "PASSED"

        # Format duration
        duration = self.duration_seconds
        duration_str = f"{duration / 60:.1f}m" if duration >= 60 else f"{duration:.1f}s"

        # Format timestamp (human readable)
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(self.started_at)
            time_str = start_dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = self.started_at[:16]

        # Header with status
        lines = [
            f"# {status_icon} {self.config_name} — {status_text}",
            "",
            f"> {time_str} · {duration_str} · "
            f"{self.devices_passed}/{self.total_devices} devices · "
            f"{self.checks_passed}/{self.total_checks} checks",
            "",
        ]

        # Critical issues (grouped by device)
        if self.critical_violations:
            lines.append("## 🔴 Critical Issues\n")
            self._append_grouped_violations(lines, self.critical_violations)

        # Warnings (grouped by device)
        if self.warning_violations:
            lines.append("## 🟡 Warnings\n")
            self._append_grouped_violations(lines, self.warning_violations)

        # All passed message
        if not self.critical_violations and not self.warning_violations:
            lines.extend([
                "## ✅ All Checks Passed",
                "",
            ])

        # Detailed results table (verbose mode)
        if verbose and self.check_results:
            lines.extend(self._build_details_section())

        return "\n".join(lines)

    def _build_details_section(self) -> list[str]:
        """Build detailed check results section."""
        from collections import defaultdict

        lines = [
            "## 📊 Check Details",
            "",
        ]

        # Group results by check name
        by_check: dict[str, list[CheckResult]] = defaultdict(list)
        for r in self.check_results:
            by_check[r.check_name].append(r)

        # Build table for each check
        for check_name, results in by_check.items():
            # Count pass/fail
            passed = sum(1 for r in results if r.success)
            total = len(results)
            status = "✅" if passed == total else "⚠️"

            lines.append(f"### {status} {check_name} ({passed}/{total})")
            lines.append("")

            # Table header
            lines.append("| Device | Status | Summary |")
            lines.append("|--------|--------|---------|")

            # Table rows
            for r in sorted(results, key=lambda x: x.device):
                icon = "✅" if r.success else "❌"
                # Format value for readability
                summary = self._format_check_value(r.actual_value)
                lines.append(f"| {r.device} | {icon} | {summary} |")

            lines.append("")

        return lines

    def _format_check_value(self, value: Any) -> str:
        """Format check value for human-readable display."""
        if value is None:
            return "-"

        # Handle list of dicts (common SuzieQ summarize output)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            d = value[0]
            parts = []

            # Extract key metrics
            if "total_records" in d:
                parts.append(f"{d['total_records']} records")
            if "unique_hosts" in d:
                hosts = d["unique_hosts"]
                if hosts > 0:
                    parts.append(f"{hosts} hosts")

            # State counts (BGP, OSPF, etc.)
            for key in ["state_counts", "status_counts", "adminState_counts"]:
                if d.get(key):
                    counts = d[key]
                    # Format: "2 Established, 1 Active"
                    state_parts = [f"{v} {k}" for k, v in counts.items()]
                    parts.extend(state_parts)

            return ", ".join(parts) if parts else "OK"

        # Handle dict directly
        if isinstance(value, dict):
            if "total_records" in value:
                return f"{value['total_records']} records"
            return "OK"

        # Simple values
        s = str(value)
        if len(s) > 40:
            return s[:37] + "..."
        return s

    def _append_grouped_violations(
        self,
        lines: list[str],
        violations: list[CheckResult],
    ) -> None:
        """Group violations by device for cleaner display."""
        from collections import defaultdict

        # Group by device
        by_device: dict[str, list[CheckResult]] = defaultdict(list)
        for v in violations:
            by_device[v.device].append(v)

        # Output grouped
        for device, checks in sorted(by_device.items()):
            if len(checks) == 1:
                # Single issue: inline format
                c = checks[0]
                lines.append(f"- **{device}**: {c.message or c.check_name}")
            else:
                # Multiple issues: nested format
                lines.append(f"- **{device}** ({len(checks)} issues)")
                for c in checks:
                    lines.append(f"  - {c.message or c.check_name}")
        lines.append("")

    def save(self, output_dir: Path | str | None = None) -> Path:
        """Save report to file.

        Args:
            output_dir: Optional output directory. Defaults to inspection_reports_dir.

        Returns:
            Path to saved report file.
        """
        from pathlib import Path

        from config.settings import get_path

        # Use provided dir or default
        if output_dir:
            reports_dir = Path(output_dir)
            reports_dir.mkdir(parents=True, exist_ok=True)
        else:
            reports_dir = get_path("inspection_reports")

        # Generate filename: inspection_{name}_{timestamp}.md
        # Sanitize config name for filename
        safe_name = self.config_name.lower().replace(" ", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")

        # Parse timestamp
        try:
            ts = datetime.fromisoformat(self.started_at)
            ts_str = ts.strftime("%Y%m%d_%H%M%S")
        except Exception:
            ts_str = self.started_at[:19].replace(":", "").replace("-", "")

        filename = f"inspection_{safe_name}_{ts_str}.md"
        report_path = reports_dir / filename

        # Write report
        content = self.to_markdown()
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)

        return report_path


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

        Priority:
        1. explicit_devices (if non-empty) → use hardcoded list
        2. netbox_filter (if non-empty) → query NetBox API
        3. Both empty → fallback to SuzieQ device table

        Args:
            device_filter: Device filter configuration.

        Returns:
            List of device hostnames.
        """
        # Priority 1: Explicit devices take priority
        if device_filter.explicit_devices:
            logger.info(
                f"Using explicit device list: {device_filter.explicit_devices}"
            )
            return device_filter.explicit_devices

        # Priority 2: Query NetBox if filter provided
        if device_filter.netbox_filter:
            devices = await self._resolve_from_netbox(device_filter)
            if devices:
                return devices

        # Priority 3: Fallback to SuzieQ device table
        return await self._resolve_from_suzieq()

    async def _resolve_from_netbox(self, device_filter: DeviceFilter) -> list[str]:
        """Query NetBox for devices matching filter."""
        try:
            from olav.tools.netbox_tool import NetBoxAPITool

            netbox = NetBoxAPITool()

            # Build NetBox API params
            params = self._build_netbox_params(device_filter.netbox_filter)
            params["limit"] = 100

            logger.info(f"Querying NetBox with filter: {params}")

            result = await netbox.execute(
                path="/api/dcim/devices/",
                method="GET",
                params=params,
            )

            if result.error:
                logger.warning(f"NetBox query error: {result.error}")
                return []

            if not result.data:
                logger.warning("NetBox returned no devices")
                return []

            # Extract device names
            devices = [
                d["name"]
                for d in result.data
                if isinstance(d, dict) and "name" in d
            ]

            # Apply exclude list
            if device_filter.exclude:
                before = len(devices)
                devices = [d for d in devices if d not in device_filter.exclude]
                logger.info(
                    f"Excluded {before - len(devices)} devices: "
                    f"{device_filter.exclude}"
                )

            logger.info(f"NetBox resolved {len(devices)} devices: {devices}")
            return devices

        except Exception as e:
            logger.warning(f"Failed to query NetBox: {e}")
            return []

    def _build_netbox_params(self, filter_config: dict[str, Any]) -> dict[str, Any]:
        """Build NetBox API query parameters from filter config."""
        params: dict[str, Any] = {}

        # Default to active devices
        if "status" not in filter_config:
            params["status"] = "active"

        # Map filter fields to NetBox API params
        field_mapping = {
            "tag": "tag",
            "role": "role",
            "site": "site",
            "status": "status",
            "platform": "platform",
            "tenant": "tenant",
            "region": "region",
        }

        for config_key, api_key in field_mapping.items():
            if config_key in filter_config:
                params[api_key] = filter_config[config_key]

        return params

    async def _resolve_from_suzieq(self) -> list[str]:
        """Fallback: get all devices from SuzieQ."""
        try:
            from olav.tools.suzieq_tool import SuzieQTool

            sq = SuzieQTool()
            result = await sq.execute(table="device", method="get")

            if result.data:
                devices = list({r["hostname"] for r in result.data if "hostname" in r})
                logger.info(f"SuzieQ fallback resolved {len(devices)} devices")
                return devices
        except Exception as e:
            logger.warning(f"SuzieQ fallback failed: {e}")

        return []

    async def compile_check(self, check: CheckConfig) -> tuple[str, dict[str, Any], ThresholdConfig | None]:
        """Compile check to tool/parameters using IntentCompiler if needed.

        Args:
            check: Check configuration.

        Returns:
            Tuple of (tool_name, parameters, threshold_config, query_plan).
            query_plan is included for multi-source execution.
        """
        from olav.modes.inspection.compiler import IntentCompiler, QueryPlan

        # Explicit mode: use provided tool/parameters directly
        if check.is_explicit_mode:
            # Determine source based on tool name
            tool = check.tool or "suzieq_query"
            if tool == "suzieq_query":
                source = "suzieq"
            elif tool == "cli_show":
                source = "cli"
            elif tool == "netconf_get":
                source = "openconfig"
            else:
                source = "unknown"

            # Create a synthetic QueryPlan for explicit mode
            plan = QueryPlan(
                table=check.parameters.get("table", "device"),
                method=check.parameters.get("method", "get"),
                filters={k: v for k, v in check.parameters.items() if k not in ("table", "method")},
                source=source,
                read_only=True,
            )
            return tool, check.parameters, check.threshold, plan

        # Intent mode: use IntentCompiler
        if check.is_intent_mode and check.intent:
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
                    message=f"{{device}}: {plan.validation.field} does not satisfy condition {plan.validation.operator} {plan.validation.expected}",
                )

            # Return tool based on source
            tool_name = self._get_tool_name_for_source(plan)
            return tool_name, parameters, threshold, plan

        # Fallback: use description as intent
        if check.description:
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
                    message=f"{{device}}: {plan.validation.field} does not satisfy condition",
                )

            tool_name = self._get_tool_name_for_source(plan)
            return tool_name, parameters, threshold, plan

        # No intent or tool specified - error
        msg = f"Check '{check.name}' must have either 'intent' or 'tool' specified"
        raise ValueError(msg)

    def _get_tool_name_for_source(self, plan: QueryPlan) -> str:
        """Get tool name based on query plan source.

        Args:
            plan: The compiled query plan.

        Returns:
            Tool name string.
        """
        if plan.source == "suzieq":
            return "suzieq_query"
        if plan.source == "cli":
            return plan.fallback_tool or "cli_show"
        if plan.source == "openconfig":
            return plan.fallback_tool or "netconf_get"
        return "suzieq_query"

    async def execute_check(
        self,
        device: str,
        check: CheckConfig,
    ) -> CheckResult:
        """Execute a single check on a device.

        Supports multiple data sources:
        - SuzieQ (parquet data)
        - CLI (show commands)
        - OpenConfig (NETCONF get)

        Args:
            device: Device hostname.
            check: Check configuration.

        Returns:
            CheckResult with findings.
        """
        import time

        start = time.perf_counter()

        try:
            # Compile check to tool/parameters/plan
            _tool_name, parameters, threshold, plan = await self.compile_check(check)

            # Execute based on data source
            if plan.source == "suzieq":
                result = await self._execute_suzieq(device, parameters)
            elif plan.source == "cli":
                result = await self._execute_cli(device, plan)
            elif plan.source == "openconfig":
                result = await self._execute_openconfig(device, plan)
            else:
                return CheckResult(
                    device=device,
                    check_name=check.name,
                    success=False,
                    error=f"Unknown source: {plan.source}",
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

    async def _execute_suzieq(
        self,
        device: str,
        parameters: dict[str, Any],
    ) -> Any:
        """Execute SuzieQ query.

        Args:
            device: Device hostname.
            parameters: Query parameters (table, method, filters).

        Returns:
            Query result data.
        """
        from olav.tools.suzieq_tool import SuzieQTool

        tool = SuzieQTool()
        params = {
            **parameters,
            "hostname": device,
        }
        result = await tool.execute(**params)

        # SuzieQTool returns ToolOutput, extract data
        if hasattr(result, "data"):
            return result.data
        return result

    async def _execute_cli(
        self,
        device: str,
        plan: QueryPlan,
    ) -> Any:
        """Execute CLI show command.

        Args:
            device: Device hostname.
            plan: Query plan with fallback_params.

        Returns:
            Command output.
        """
        if not plan.fallback_params or "command" not in plan.fallback_params:
            msg = "CLI execution requires 'command' in fallback_params"
            raise ValueError(msg)

        command = plan.fallback_params["command"]

        # Safety check: must be a show command
        if not command.strip().lower().startswith("show "):
            msg = f"Only 'show' commands are allowed, got: {command}"
            raise ValueError(msg)

        logger.info(f"[Inspection] Executing CLI on {device}: {command}")

        # Use StandardModeExecutor for CLI execution (reuse existing infrastructure)
        from olav.core.unified_classifier import UnifiedClassificationResult
        from olav.modes.standard.executor import StandardModeExecutor
        from olav.tools.base import ToolRegistry

        classification = UnifiedClassificationResult(
            intent_category="query",
            tool="nornir_show",
            parameters={
                "hostname": device,
                "command": command,
            },
            confidence=1.0,
            reasoning="Inspection mode CLI fallback",
        )

        executor = StandardModeExecutor(
            tool_registry=ToolRegistry(),
            yolo_mode=True,  # show commands don't need HITL
        )

        result = await executor.execute(classification, user_query=command)
        return result.raw_output

    async def _execute_openconfig(
        self,
        device: str,
        plan: QueryPlan,
    ) -> Any:
        """Execute OpenConfig NETCONF get.

        Args:
            device: Device hostname.
            plan: Query plan with fallback_params.

        Returns:
            NETCONF get result.
        """
        if not plan.fallback_params or "xpath" not in plan.fallback_params:
            msg = "OpenConfig execution requires 'xpath' in fallback_params"
            raise ValueError(msg)

        xpath = plan.fallback_params["xpath"]
        datastore = plan.fallback_params.get("datastore", "running")

        logger.info(f"[Inspection] Executing NETCONF get on {device}: {xpath}")

        # Use StandardModeExecutor for NETCONF execution
        from olav.core.unified_classifier import UnifiedClassificationResult
        from olav.modes.standard.executor import StandardModeExecutor
        from olav.tools.base import ToolRegistry

        classification = UnifiedClassificationResult(
            intent_category="query",
            tool="netconf_get",
            parameters={
                "hostname": device,
                "xpath": xpath,
                "datastore": datastore,
            },
            confidence=1.0,
            reasoning="Inspection mode OpenConfig fallback",
        )

        executor = StandardModeExecutor(
            tool_registry=ToolRegistry(),
            yolo_mode=True,  # get operations don't need HITL
        )

        result = await executor.execute(classification, user_query=xpath)
        return result.raw_output

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
    save_report: bool = True,
) -> InspectionResult:
    """Run inspection from YAML config.

    Convenience function for running inspection without class instantiation.

    Args:
        config_path: Path to YAML config.
        debug: Whether to enable debug mode.
        max_parallel: Max parallel device checks.
        save_report: Whether to auto-save report to data/reports/inspection/.

    Returns:
        InspectionResult with findings.

    Example:
        result = await run_inspection("config/inspections/daily_core_check.yaml")
        print(result.to_markdown())
    """
    controller = InspectionModeController(max_parallel_devices=max_parallel)

    if debug:
        async with DebugContext(enabled=True) as ctx:
            result = await controller.run(config_path, ctx)
    else:
        result = await controller.run(config_path)

    # Auto-save report
    if save_report:
        report_path = result.save()
        logger.info(f"📄 Report saved: {report_path}")

    return result
