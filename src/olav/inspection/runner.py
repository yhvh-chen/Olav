"""Inspection Runner - Execute batch inspections without HITL.

This module provides automated network inspection capabilities:
- Load inspection profiles from YAML config
- Execute checks in parallel across devices
- Generate timestamped Markdown reports
- Support scheduled/periodic execution

Usage:
    # One-shot run
    uv run python -m olav.main inspect --profile daily_core_check

    # Run with specific profile file
    uv run python -m olav.main inspect --config config/inspections/daily_core_check.yaml

    # Start scheduler daemon
    uv run python -m olav.main inspect --daemon
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from config.settings import AgentConfig, InspectionConfig

from olav.inspection.report import ReportGenerator

logger = logging.getLogger("olav.inspection")


class CheckResult:
    """Result of a single inspection check."""

    def __init__(
        self,
        check_name: str,
        device: str,
        passed: bool,
        severity: str,
        message: str,
        data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.check_name = check_name
        self.device = device
        self.passed = passed
        self.severity = severity  # "critical", "warning", "info"
        self.message = message
        self.data = data or {}
        self.error = error
        self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "device": self.device,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class InspectionRunner:
    """Execute batch network inspections.

    This runner:
    1. Loads inspection profile from YAML
    2. Resolves target devices (from list, NetBox filter, or regex)
    3. Executes checks in parallel
    4. Generates Markdown report with timestamp
    """

    def __init__(
        self,
        profile_name: str | None = None,
        config_path: Path | str | None = None,
        language: str = "zh",
    ) -> None:
        """Initialize inspection runner.

        Args:
            profile_name: Name of profile in config/inspections/ (without .yaml)
            config_path: Direct path to config file (overrides profile_name)
            language: Output language for reports ("zh", "en", "ja")
        """
        self.language = language
        AgentConfig.LANGUAGE = language  # type: ignore

        if config_path:
            self.config_path = Path(config_path)
        elif profile_name:
            self.config_path = Path("config/inspections") / f"{profile_name}.yaml"
        else:
            self.config_path = (
                Path("config/inspections") / f"{InspectionConfig.DEFAULT_PROFILE}.yaml"
            )

        self.config: dict[str, Any] = {}
        self.results: list[CheckResult] = []
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

        # Lazy load SuzieQ tool
        self._suzieq_query = None

    def _get_suzieq_tool(self):
        """Lazy load SuzieQ query tool."""
        if self._suzieq_query is None:
            from olav.tools.suzieq_parquet_tool import suzieq_query

            self._suzieq_query = suzieq_query
        return self._suzieq_query

    def load_config(self) -> dict[str, Any]:
        """Load inspection profile from YAML."""
        if not self.config_path.exists():
            msg = f"Inspection profile not found: {self.config_path}"
            raise FileNotFoundError(msg)

        with open(self.config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        logger.info(f"Loaded inspection profile: {self.config.get('name', 'unknown')}")
        return self.config

    async def resolve_devices(self) -> list[str]:
        """Resolve target devices from config.

        Supports:
        - Explicit list: devices: ["R1", "R2"]
        - NetBox filter: devices.netbox_filter: {role: router}
        - Regex pattern: devices.regex: "^R[0-9]+"
        """
        devices_config = self.config.get("devices", [])

        # Case 1: Explicit list
        if isinstance(devices_config, list):
            return devices_config

        # Case 2: Dict with filter options
        if isinstance(devices_config, dict):
            # NetBox filter
            if "netbox_filter" in devices_config:
                # TODO: Query NetBox for devices matching filter
                # For now, use SuzieQ device table as fallback
                suzieq = self._get_suzieq_tool()
                # Use 'get' method and extract unique hostnames from data
                result = await suzieq.ainvoke({"table": "device", "method": "get"})
                if isinstance(result, dict) and "data" in result:
                    hostnames = set()
                    for d in result["data"]:
                        if isinstance(d, dict) and d.get("hostname"):
                            hostnames.add(d.get("hostname"))
                    return list(hostnames)
                return []

            # Regex pattern
            if "regex" in devices_config:
                import re

                pattern = devices_config["regex"]
                suzieq = self._get_suzieq_tool()
                # Use 'get' method and filter by regex
                result = await suzieq.ainvoke({"table": "device", "method": "get"})
                if isinstance(result, dict) and "data" in result:
                    all_devices = set()
                    for d in result["data"]:
                        if isinstance(d, dict) and d.get("hostname"):
                            all_devices.add(d.get("hostname"))
                    return [d for d in all_devices if re.match(pattern, d)]
                return []

        # Fallback: Get all devices from SuzieQ
        suzieq = self._get_suzieq_tool()
        result = await suzieq.ainvoke({"table": "device", "method": "get"})
        if isinstance(result, dict) and "data" in result:
            hostnames = set()
            for d in result["data"]:
                if isinstance(d, dict) and d.get("hostname"):
                    hostnames.add(d.get("hostname"))
            return list(hostnames)
        return []

    async def execute_check(
        self,
        check: dict[str, Any],
        device: str,
    ) -> CheckResult:
        """Execute a single check on a device.

        Args:
            check: Check configuration from YAML
            device: Target device hostname

        Returns:
            CheckResult with pass/fail status
        """
        check_name = check.get("name", "unknown")
        tool = check.get("tool", "suzieq_query")
        params = check.get("parameters", {}).copy()
        threshold = check.get("threshold", {})

        try:
            # Add device filter to query
            params["hostname"] = device

            # Execute tool
            if tool == "suzieq_query":
                suzieq = self._get_suzieq_tool()
                result = await suzieq.ainvoke(params)
            else:
                # Unsupported tool
                return CheckResult(
                    check_name=check_name,
                    device=device,
                    passed=False,
                    severity="warning",
                    message=f"Unsupported tool: {tool}",
                )

            # Evaluate threshold
            if threshold:
                passed, message = self._evaluate_threshold(result, threshold, device)
                severity = threshold.get("severity", "warning")
            else:
                # No threshold = info check
                passed = True
                severity = "info"
                message = f"Check completed: {check_name}"

            return CheckResult(
                check_name=check_name,
                device=device,
                passed=passed,
                severity=severity if not passed else "info",
                message=message,
                data=result if isinstance(result, dict) else {"raw": str(result)[:500]},
            )

        except Exception as e:
            logger.error(f"Check {check_name} failed on {device}: {e}")
            return CheckResult(
                check_name=check_name,
                device=device,
                passed=False,
                severity="critical",
                message=f"Check execution error: {e}",
                error=str(e),
            )

    def _evaluate_threshold(
        self,
        result: dict[str, Any],
        threshold: dict[str, Any],
        device: str,
    ) -> tuple[bool, str]:
        """Evaluate threshold condition against result.

        Args:
            result: Tool execution result
            threshold: Threshold config from YAML
            device: Device hostname for message formatting

        Returns:
            (passed, message) tuple
        """
        field = threshold.get("field", "count")
        operator = threshold.get("operator", ">=")
        expected = threshold.get("value", 0)
        message_template = threshold.get("message", "Check {field} {operator} {value}")

        # Extract actual value from result
        actual = result.get(field)
        if actual is None and "data" in result:
            # Try to get from data list
            if isinstance(result["data"], list):
                actual = len(result["data"])
            elif isinstance(result["data"], dict):
                actual = result["data"].get(field)

        if actual is None:
            actual = result.get("count", 0)

        # Evaluate operator
        operators = {
            "==": lambda a, e: a == e,
            "!=": lambda a, e: a != e,
            ">": lambda a, e: a > e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            "<=": lambda a, e: a <= e,
            "in": lambda a, e: a in e,
            "not_in": lambda a, e: a not in e,
        }

        eval_func = operators.get(operator)
        if not eval_func:
            return False, f"Unknown operator: {operator}"

        try:
            passed = eval_func(actual, expected)
        except Exception as e:
            return False, f"Threshold evaluation error: {e}"

        # Format message
        message = message_template.format(
            device=device,
            field=field,
            operator=operator,
            value=expected,
            actual=actual,
        )

        return passed, message

    async def run(self) -> dict[str, Any]:
        """Execute full inspection run.

        Returns:
            Summary dict with results and report path
        """
        self.start_time = datetime.now()
        self.results = []

        # Load config
        self.load_config()

        profile_name = self.config.get("name", "inspection")
        description = self.config.get("description", "")
        logger.info(f"Starting inspection: {profile_name}")
        logger.info(f"Description: {description}")

        # Resolve devices
        devices = await self.resolve_devices()
        if not devices:
            logger.warning("No devices found for inspection")
            return {"status": "error", "message": "No devices found"}

        logger.info(
            f"Target devices ({len(devices)}): {', '.join(devices[:5])}{'...' if len(devices) > 5 else ''}"
        )

        # Get enabled checks
        checks = [c for c in self.config.get("checks", []) if c.get("enabled", True)]
        if not checks:
            logger.warning("No enabled checks in profile")
            return {"status": "error", "message": "No enabled checks"}

        logger.info(f"Running {len(checks)} checks on {len(devices)} devices")

        # Execute checks in parallel (limited concurrency)
        semaphore = asyncio.Semaphore(InspectionConfig.PARALLEL_DEVICES)

        async def run_with_semaphore(check: dict, device: str) -> CheckResult:
            async with semaphore:
                return await self.execute_check(check, device)

        # Create all tasks
        tasks = []
        for check in checks:
            for device in devices:
                tasks.append(run_with_semaphore(check, device))

        # Execute all
        self.results = await asyncio.gather(*tasks)

        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        # Count results
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        critical = sum(1 for r in self.results if not r.passed and r.severity == "critical")

        logger.info(
            f"Inspection completed in {duration:.1f}s: {passed} passed, {failed} failed ({critical} critical)"
        )

        # Generate report
        report_generator = ReportGenerator(
            profile_name=profile_name,
            description=description,
            results=self.results,
            start_time=self.start_time,
            end_time=self.end_time,
            devices=devices,
            checks=checks,
            language=self.language,
        )

        report_path = report_generator.generate()
        logger.info(f"Report saved: {report_path}")

        return {
            "status": "success",
            "profile": profile_name,
            "duration_seconds": duration,
            "total_checks": len(self.results),
            "passed": passed,
            "failed": failed,
            "critical": critical,
            "report_path": str(report_path),
        }


async def run_inspection(
    profile: str | None = None,
    config_path: str | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    """Convenience function to run inspection.

    Args:
        profile: Profile name (e.g., "daily_core_check")
        config_path: Direct path to config file
        language: Output language

    Returns:
        Summary dict with results
    """
    runner = InspectionRunner(
        profile_name=profile,
        config_path=config_path,
        language=language,
    )
    return await runner.run()
