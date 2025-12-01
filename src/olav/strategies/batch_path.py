"""
Batch Path Strategy - YAML-driven parallel batch inspection with zero-LLM validation.

This strategy executes batch compliance checks across multiple devices
using declarative YAML configuration. Key features:
- Parallel execution across devices (asyncio)
- Zero-LLM threshold validation (deterministic)
- Consolidated reporting (pass/fail summary + violations)

Execution Flow:
1. Load InspectionConfig from YAML file
2. Resolve device list (explicit, NetBox filter, or regex)
3. Execute tools in parallel across devices
4. Validate results with ThresholdValidator (no LLM)
5. Generate consolidated report (table/JSON/YAML)

Example YAML Config:
```yaml
name: bgp_health_check
description: Verify BGP peer health across all routers
devices:
  netbox_filter:
    role: router
    tag: production
checks:
  - name: bgp_peer_count
    tool: suzieq_query
    parameters:
      table: bgp
      state: Established
    threshold:
      field: count
      operator: ">="
      value: 2
      severity: critical
parallel: true
max_workers: 10
```

Key Difference from Other Strategies:
- Fast Path: Single device, single tool, instant response
- Deep Path: Complex reasoning, iterative, diagnostic focus
- Batch Path: Multi-device, parallel, compliance focus, zero-LLM validation
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from olav.core.prompt_manager import prompt_manager
from olav.schemas.inspection import CheckTask, InspectionConfig
from olav.tools.base import ToolOutput, ToolRegistry
from olav.validation.threshold import DeviceValidationResult, ThresholdValidator

logger = logging.getLogger(__name__)


class DeviceCheckResult(BaseModel):
    """
    Result of executing a single check on a single device.

    Contains both the raw tool output and validation results.
    """

    device: str
    check_name: str
    tool_output: ToolOutput | None = None
    validation: DeviceValidationResult | None = None
    error: str | None = None
    execution_time_ms: float = 0.0


class BatchExecutionSummary(BaseModel):
    """
    Summary of batch execution results.

    Aggregates pass/fail counts and execution metrics.
    """

    total_devices: int
    total_checks: int
    total_executions: int
    passed: int
    failed: int
    errors: int
    total_execution_time_ms: float
    pass_rate: float = Field(description="Percentage of passing checks (0.0-100.0)")


class BatchPathResult(BaseModel):
    """
    Complete batch path execution result.

    Contains summary, individual results, and detailed violations.
    """

    config_name: str
    summary: BatchExecutionSummary
    device_results: list[DeviceCheckResult]
    violations: list[str] = Field(default_factory=list, description="All violation messages")

    def to_report(self, format: Literal["text", "json", "yaml"] = "text") -> str:
        """
        Generate human-readable report.

        Args:
            format: Output format (text, json, yaml)

        Returns:
            Formatted report string
        """
        if format == "text":
            return self._generate_text_report()
        if format == "json":
            return self.model_dump_json(indent=2)
        if format == "yaml":
            import yaml

            return yaml.dump(self.model_dump(), default_flow_style=False)
        msg = f"Unsupported format: {format}"
        raise ValueError(msg)

    def _generate_text_report(self) -> str:
        """Generate text table report."""
        lines = [
            "═══════════════════════════════════════════════════",
            f"Batch Inspection Report: {self.config_name}",
            "═══════════════════════════════════════════════════",
            "",
            "Summary:",
            f"  Total Devices: {self.summary.total_devices}",
            f"  Total Checks: {self.summary.total_checks}",
            f"  Total Executions: {self.summary.total_executions}",
            f"  Passed: {self.summary.passed} ✓",
            f"  Failed: {self.summary.failed} ✗",
            f"  Errors: {self.summary.errors} ⚠",
            f"  Pass Rate: {self.summary.pass_rate:.1f}%",
            f"  Total Time: {self.summary.total_execution_time_ms:.0f}ms",
            "",
        ]

        if self.violations:
            lines.append("Violations:")
            for violation in self.violations:
                lines.append(f"  • {violation}")
            lines.append("")

        lines.append("Detailed Results:")
        lines.append(f"{'Device':<20} {'Check':<30} {'Status':<10} {'Time(ms)':<10}")
        lines.append("-" * 70)

        for result in self.device_results:
            if result.error:
                status = "ERROR"
            elif result.validation and not result.validation.passed:
                status = "FAILED"
            else:
                status = "PASSED"

            lines.append(
                f"{result.device:<20} {result.check_name:<30} "
                f"{status:<10} {result.execution_time_ms:<10.0f}"
            )

        return "\n".join(lines)


class BatchPathStrategy:
    """
    Batch Path execution strategy for parallel compliance checks.

    Implements YAML-driven batch inspection with:
    1. Device list resolution (explicit, NetBox, regex)
    2. Parallel tool execution
    3. Zero-LLM threshold validation
    4. Consolidated reporting

    This strategy does NOT use LLM for validation - all threshold
    checks use pure Python operators for deterministic results.

    Attributes:
        llm: Language model (used only for device selection with NetBox)
        validator: ThresholdValidator for deterministic validation
        tool_registry: ToolRegistry for tool access
    """

    def __init__(self, llm: BaseChatModel, tool_registry: ToolRegistry | None = None) -> None:
        """
        Initialize BatchPathStrategy.

        Args:
            llm: Language model (minimal use - only for NetBox queries and intent compilation)
            tool_registry: ToolRegistry instance (default: global registry)
        """
        self.llm = llm
        self.validator = ThresholdValidator()
        self.tool_registry = tool_registry or ToolRegistry

        # Load tool capability guides (cached at init)
        self._tool_guides = self._load_tool_capability_guides()

    def _load_tool_capability_guides(self) -> dict[str, str]:
        """Load tool capability guides from config/prompts/tools/.

        Returns:
            Dict mapping tool prefix to capability guide content
        """
        from olav.core.prompt_manager import prompt_manager

        guides = {}
        for tool_prefix in ["suzieq", "netbox", "cli", "netconf"]:
            guide = prompt_manager.load_tool_capability_guide(tool_prefix)
            if guide:
                guides[tool_prefix] = guide

        return guides

    @classmethod
    def load_config(cls, config_path: str | Path) -> InspectionConfig:
        """
        Load inspection configuration from YAML file.

        Convenience method for loading YAML configs without instantiating strategy.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            InspectionConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If YAML is invalid

        Example:
            >>> config = BatchPathStrategy.load_config("config/inspections/bgp_audit.yaml")
            >>> print(f"Loaded: {config.name}")
            >>> print(f"Devices: {config.devices}")
            >>> print(f"Checks: {len(config.checks)}")
        """
        return InspectionConfig.from_yaml(Path(config_path))

    async def execute(
        self, config_path: str | None = None, config_dict: dict[str, Any] | None = None
    ) -> BatchPathResult:
        """
        Execute batch inspection from YAML config or dict.

        Args:
            config_path: Path to YAML config file
            config_dict: Config as dictionary (alternative to file)

        Returns:
            BatchPathResult with summary and detailed results

        Raises:
            ValueError: If neither config_path nor config_dict provided
        """
        # Load configuration
        if config_path:
            config = InspectionConfig.from_yaml(Path(config_path))
        elif config_dict:
            config = InspectionConfig(**config_dict)
        else:
            msg = "Must provide either config_path or config_dict"
            raise ValueError(msg)

        logger.info(f"Starting batch inspection: {config.name}")

        # Resolve device list
        devices = await self._resolve_devices(config)
        logger.info(f"Resolved {len(devices)} devices: {devices}")

        # Get enabled checks
        enabled_checks = config.get_enabled_checks()
        logger.info(f"Enabled checks: {[c.name for c in enabled_checks]}")

        # Execute checks
        import time

        start_time = time.perf_counter()

        if config.parallel:
            results = await self._execute_parallel(devices, enabled_checks, config.max_workers)
        else:
            results = await self._execute_sequential(devices, enabled_checks)

        total_time = (time.perf_counter() - start_time) * 1000

        # Generate summary
        summary = self._generate_summary(results, len(devices), len(enabled_checks), total_time)

        # Collect violations
        violations = []
        for result in results:
            if result.validation:
                for val_result in result.validation.results:
                    if not val_result.passed and val_result.violation_message:
                        violations.append(val_result.violation_message)

        return BatchPathResult(
            config_name=config.name, summary=summary, device_results=results, violations=violations
        )

    async def _resolve_devices(self, config: InspectionConfig) -> list[str]:
        """
        Resolve device list from config.

        Supports three methods:
        1. Explicit list: devices as list[str]
        2. NetBox filter: devices.netbox_filter (requires LLM to build query)
        3. Regex pattern: devices.regex (match against inventory)

        Args:
            config: InspectionConfig with device selector

        Returns:
            List of device hostnames
        """
        # Handle explicit list (list[str])
        if isinstance(config.devices, list):
            return config.devices

        # Handle DeviceSelector object
        if config.devices.explicit:
            return config.devices.explicit

        if config.devices.netbox_filter:
            # Use NetBox tool to query devices
            netbox_tool = self.tool_registry.get_tool("netbox_api_call")
            if not netbox_tool:
                logger.warning("NetBox tool not available, returning empty device list")
                return []

            # Build NetBox query from filter
            filters = config.devices.netbox_filter
            params = {"endpoint": "/dcim/devices/", **filters}

            result = await netbox_tool.execute(**params)
            if result.error:
                logger.error(f"NetBox query failed: {result.error}")
                return []

            # Extract hostnames from NetBox response
            return [device.get("name", "") for device in result.data if device.get("name")]

        if config.devices.regex:
            # Get all devices from inventory and filter with regex
            import re

            pattern = re.compile(config.devices.regex)

            # Try to get device list from SuzieQ or NetBox
            suzieq_tool = self.tool_registry.get_tool("suzieq_query")
            if suzieq_tool:
                result = await suzieq_tool.execute(
                    table="device", method="unique", column="hostname"
                )
                if not result.error and result.data:
                    all_devices = [d.get("hostname", "") for d in result.data]
                    return [d for d in all_devices if d and pattern.match(d)]

            logger.warning("Could not resolve devices from regex - no inventory available")
            return []

        logger.warning("No device selector specified in config")
        return []

    async def _discover_schema(self, intent: str) -> dict[str, Any] | None:
        """
        Schema-Aware discovery for BatchPath.

        Args:
            intent: Natural language intent to search schema for

        Returns:
            Dict mapping table names to schema info, or None
        """
        try:
            schema_tool = self.tool_registry.get_tool("suzieq_schema_search")
            if not schema_tool:
                return None

            from olav.tools.base import ToolOutput

            result = await schema_tool.execute(query=intent)

            if isinstance(result, ToolOutput) and result.data:
                schema_context = {}
                data = result.data

                if isinstance(data, dict):
                    tables = data.get("tables", [])
                    for table in tables:
                        if table in data:
                            schema_context[table] = data[table]
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "table" in item:
                            schema_context[item["table"]] = item

                if schema_context:
                    logger.debug(f"BatchPath schema discovery found: {list(schema_context.keys())}")
                    return schema_context

            return None

        except Exception as e:
            logger.warning(f"Schema discovery failed: {e}")
            return None

    async def _compile_intent_to_parameters(
        self, intent: str, tool: str, existing_params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Compile natural language intent to tool parameters using LLM.

        Uses Schema-Aware pattern to discover correct table names.

        This method enables YAML configs to use natural language descriptions
        instead of explicit SQL queries or XPath expressions. The LLM translates
        intent into tool-specific parameters.

        Examples:
            Intent: "<用户意图>" + tool: <工具名>
            → {<参数名>: "<参数值>"}  # 使用 Schema Discovery 发现的表名

        Args:
            intent: Natural language description of what to check
            tool: Tool name (suzieq_query, cli_execute, netconf_get)
            existing_params: Existing parameters from YAML (will be merged)

        Returns:
            Updated parameters dictionary with LLM-compiled values
        """
        # Schema-Aware: discover correct table names
        schema_section = ""
        if tool == "suzieq_query":
            schema_context = await self._discover_schema(intent)
            if schema_context:
                schema_tables = "\n".join(
                    [
                        f"    - {table}: {info.get('description', '')} (fields: {', '.join(info.get('fields', [])[:5])}...)"
                        for table, info in schema_context.items()
                    ]
                )
                schema_section = f"""
## 🎯 Schema Discovery Results (MUST use these table names)
{schema_tables}

⚠️ IMPORTANT: Use the table names discovered above - DO NOT guess!
"""

        # Build capability guide section for this tool
        capability_guide = ""
        tool_prefix = tool.split("_")[0] if "_" in tool else tool
        if tool_prefix in self._tool_guides:
            capability_guide = f"""
## Tool Capability Reference
{self._tool_guides[tool_prefix][:800]}...
"""

        try:
            system_prompt = prompt_manager.load_prompt(
                "strategies/batch_path",
                "intent_compilation",
                tool=tool,
                schema_section=schema_section,
                capability_guide=capability_guide,
                intent=intent,
                existing_params=str(existing_params),
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Failed to load intent_compilation prompt: {e}, using fallback")
            system_prompt = f"Compile intent '{intent}' for tool {tool} into parameters."

        human_prompt = f"Intent: {intent}\n\nExisting parameters: {existing_params}\n\nReturn ONLY JSON."

        try:
            response = await self.llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
            )

            # Parse JSON response
            import json
            import re

            # Extract JSON from response (handle code blocks)
            content = response.content
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                compiled_params = json.loads(json_match.group())
                # Merge with existing params (existing takes precedence)
                merged = {**compiled_params, **existing_params}
                logger.info(f"Compiled intent '{intent}' → {merged}")
                return merged
            logger.warning(f"LLM response did not contain valid JSON: {content}")
            return existing_params

        except Exception as e:
            logger.exception(f"Failed to compile intent '{intent}': {e}")
            return existing_params

    async def _execute_parallel(
        self, devices: list[str], checks: list[CheckTask], max_workers: int
    ) -> list[DeviceCheckResult]:
        """
        Execute checks in parallel across devices.

        Uses asyncio semaphore to limit concurrent executions.

        Args:
            devices: List of device hostnames
            checks: List of enabled checks
            max_workers: Maximum concurrent executions

        Returns:
            List of DeviceCheckResult
        """
        semaphore = asyncio.Semaphore(max_workers)

        async def execute_with_semaphore(device: str, check: CheckTask) -> DeviceCheckResult:
            async with semaphore:
                return await self._execute_single_check(device, check)

        # Create tasks for all device-check combinations
        tasks = [execute_with_semaphore(device, check) for device in devices for check in checks]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Task failed with exception: {result}")
            else:
                valid_results.append(result)

        return valid_results

    async def _execute_sequential(
        self, devices: list[str], checks: list[CheckTask]
    ) -> list[DeviceCheckResult]:
        """
        Execute checks sequentially (for debugging or rate-limited environments).

        Args:
            devices: List of device hostnames
            checks: List of enabled checks

        Returns:
            List of DeviceCheckResult
        """
        results = []

        for device in devices:
            for check in checks:
                result = await self._execute_single_check(device, check)
                results.append(result)

        return results

    async def _execute_single_check(self, device: str, check: CheckTask) -> DeviceCheckResult:
        """
        Execute a single check on a single device.

        If check has 'intent' field, compile it to parameters first using LLM.
        Otherwise, use explicit parameters from YAML.

        Args:
            device: Device hostname
            check: CheckTask to execute

        Returns:
            DeviceCheckResult with tool output and validation
        """
        start_time = time.time()

        try:
            # Get tool from registry
            tool = self.tool_registry.get_tool(check.tool)
            if not tool:
                return DeviceCheckResult(
                    device=device,
                    check_name=check.name,
                    error=f"Tool '{check.tool}' not found in registry",
                    execution_time_ms=0,
                )

            # Compile intent to parameters if provided
            params = check.parameters.copy()
            if check.intent:
                logger.info(f"Compiling intent for check '{check.name}': {check.intent}")
                params = await self._compile_intent_to_parameters(
                    intent=check.intent, tool=check.tool, existing_params=params
                )

            # Add device hostname to parameters
            params["hostname"] = device

            # Execute tool
            tool_output = await tool.execute(**params)

            execution_time = (time.time() - start_time) * 1000
            if execution_time < 1:
                execution_time = 1.0  # ensure non-zero timing for ultra-fast mock executions

            # If tool execution failed, return error
            if tool_output.error:
                return DeviceCheckResult(
                    device=device,
                    check_name=check.name,
                    tool_output=tool_output,
                    error=tool_output.error,
                    execution_time_ms=execution_time,
                )

            # Validate results with thresholds
            validation_result = None
            if check.threshold or check.thresholds:
                thresholds = check.get_all_thresholds()

                # Validate against first data item (or empty dict)
                data = tool_output.data[0] if tool_output.data else {}
                validation_result = self.validator.validate_batch(
                    data=data, rules=thresholds, device=device, check_name=check.name
                )

            return DeviceCheckResult(
                device=device,
                check_name=check.name,
                tool_output=tool_output,
                validation=validation_result,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.exception(f"Error executing check '{check.name}' on device '{device}'")
            execution_time = (time.time() - start_time) * 1000

            return DeviceCheckResult(
                device=device, check_name=check.name, error=str(e), execution_time_ms=execution_time
            )

    def _generate_summary(
        self,
        results: list[DeviceCheckResult],
        total_devices: int,
        total_checks: int,
        total_time_ms: float,
    ) -> BatchExecutionSummary:
        """
        Generate execution summary from results.

        Args:
            results: List of DeviceCheckResult
            total_devices: Number of devices checked
            total_checks: Number of checks defined
            total_time_ms: Total execution time in milliseconds

        Returns:
            BatchExecutionSummary
        """
        passed = 0
        failed = 0
        errors = 0

        for result in results:
            if result.error:
                errors += 1
            elif result.validation:
                if result.validation.passed:
                    passed += 1
                else:
                    failed += 1
            else:
                # No validation = assume passed (data collection only)
                passed += 1

        total_executions = len(results)
        pass_rate = (passed / total_executions * 100) if total_executions > 0 else 0.0

        return BatchExecutionSummary(
            total_devices=total_devices,
            total_checks=total_checks,
            total_executions=total_executions,
            passed=passed,
            failed=failed,
            errors=errors,
            total_execution_time_ms=total_time_ms,
            pass_rate=pass_rate,
        )

    @staticmethod
    def is_suitable(query: str) -> bool:
        """
        Check if query is suitable for batch path strategy.

        Batch path is suitable for:
        - Queries mentioning "batch", "all devices", "compliance"
        - Health check requests across multiple devices
        - Audit/validation tasks

        Args:
            query: User query

        Returns:
            True if batch path is appropriate
        """
        batch_keywords = [
            "batch",
            "批量",
            "all devices",
            "所有设备",
            "compliance",
            "合规",
            "audit",
            "审计",
            "health check",
            "健康检查",
            "inspect",
            "检查",
            "validate",
            "验证",
            "all routers",
            "所有路由器",
            "all switches",
            "所有交换机",
        ]

        query_lower = query.lower()
        return any(keyword in query_lower for keyword in batch_keywords)
