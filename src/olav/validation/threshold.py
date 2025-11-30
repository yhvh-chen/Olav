"""
Threshold Validator - Pure Python operator logic for zero-LLM validation.

This module implements deterministic threshold validation without LLM calls,
ensuring consistent, hallucination-free batch compliance checks.

Key Features:
- Pure Python operators (>, <, ==, !=, in, not_in)
- Type-safe comparisons with automatic coercion
- Detailed violation reporting with custom messages
- Support for numeric, string, and list comparisons

Example Usage:
```python
validator = ThresholdValidator()

rule = ThresholdRule(
    field="peer_count",
    operator=">=",
    value=2,
    severity="critical"
)

result = validator.validate(
    data={"peer_count": 1, "device": "R1"},
    rule=rule
)
# result.passed = False
# result.violation_message = "Device R1: peer_count is 1 (expected >= 2)"
```
"""

import logging
from dataclasses import dataclass
from typing import Any

from olav.schemas.inspection import ThresholdRule

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    Result of a single threshold validation.

    Attributes:
        passed: Whether validation passed
        rule: The threshold rule that was checked
        actual_value: The actual value found in data
        expected_value: The expected value from rule
        violation_message: Human-readable violation message (if failed)
    """

    passed: bool
    rule: ThresholdRule
    actual_value: Any
    expected_value: Any
    violation_message: str | None = None


@dataclass
class DeviceValidationResult:
    """
    Aggregated validation results for a single device.

    Attributes:
        device: Device hostname
        check_name: Name of the check task
        results: List of individual validation results
        passed: Overall pass/fail (all must pass)
        violations: List of violation messages
    """

    device: str
    check_name: str
    results: list[ValidationResult]

    @property
    def passed(self) -> bool:
        """Check if all validations passed."""
        return all(r.passed for r in self.results)

    @property
    def violations(self) -> list[str]:
        """Get all violation messages."""
        return [r.violation_message for r in self.results if r.violation_message]

    @property
    def critical_failures(self) -> list[ValidationResult]:
        """Get critical severity failures."""
        return [r for r in self.results if not r.passed and r.rule.severity == "critical"]


class ThresholdValidator:
    """
    Threshold validator with pure Python operator logic.

    Validates data against threshold rules without LLM calls,
    ensuring deterministic, zero-hallucination compliance checks.
    """

    def __init__(self) -> None:
        """Initialize threshold validator."""
        self._operator_map = {
            ">": self._greater_than,
            "<": self._less_than,
            ">=": self._greater_equal,
            "<=": self._less_equal,
            "==": self._equal,
            "!=": self._not_equal,
            "in": self._in_list,
            "not_in": self._not_in_list,
        }

    def validate(
        self, data: dict[str, Any], rule: ThresholdRule, device: str | None = None
    ) -> ValidationResult:
        """
        Validate data against a single threshold rule.

        Args:
            data: Data dictionary from tool output
            rule: Threshold rule to validate
            device: Optional device name for error messages

        Returns:
            ValidationResult with pass/fail and violation message
        """
        # Extract actual value from data
        actual_value = self._extract_value(data, rule.field)

        # Get operator function
        operator_func = self._operator_map.get(rule.operator)
        if not operator_func:
            logger.error(f"Unknown operator: {rule.operator}")
            return ValidationResult(
                passed=False,
                rule=rule,
                actual_value=actual_value,
                expected_value=rule.value,
                violation_message=f"Unknown operator: {rule.operator}",
            )

        # Execute comparison
        try:
            passed = operator_func(actual_value, rule.value)
        except Exception as e:
            logger.error(f"Comparison failed: {e}")
            return ValidationResult(
                passed=False,
                rule=rule,
                actual_value=actual_value,
                expected_value=rule.value,
                violation_message=f"Comparison error: {e}",
            )

        # Generate violation message if failed
        violation_message = None
        if not passed:
            violation_message = self._format_violation_message(
                rule=rule, actual_value=actual_value, device=device, data=data
            )

        return ValidationResult(
            passed=passed,
            rule=rule,
            actual_value=actual_value,
            expected_value=rule.value,
            violation_message=violation_message,
        )

    def validate_batch(
        self,
        data: dict[str, Any],
        rules: list[ThresholdRule],
        device: str | None = None,
        check_name: str = "unknown",
    ) -> DeviceValidationResult:
        """
        Validate data against multiple threshold rules.

        Args:
            data: Data dictionary from tool output
            rules: List of threshold rules
            device: Device name for reporting
            check_name: Name of the check task

        Returns:
            DeviceValidationResult with aggregated results
        """
        results = [self.validate(data, rule, device) for rule in rules]

        return DeviceValidationResult(
            device=device or "unknown", check_name=check_name, results=results
        )

    def _extract_value(self, data: dict[str, Any], field: str) -> Any:
        """
        Extract value from nested dictionary using dot notation.

        Args:
            data: Data dictionary
            field: Field path (supports dot notation: "bgp.peer_count")

        Returns:
            Extracted value or None if not found
        """
        if "." not in field:
            return data.get(field)

        # Handle nested fields
        keys = field.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return None
            else:
                return None

        return value

    def _coerce_types(self, actual: Any, expected: Any) -> tuple:
        """
        Coerce types for comparison.

        Handles string-to-number conversion and None handling.

        Args:
            actual: Actual value
            expected: Expected value

        Returns:
            Tuple of (coerced_actual, coerced_expected)
        """
        # Handle None
        if actual is None or expected is None:
            return actual, expected

        # If types already match, no coercion needed
        if type(actual) is type(expected):
            return actual, expected

        # Try numeric coercion
        if isinstance(expected, (int, float)):
            try:
                return float(actual), float(expected)
            except (ValueError, TypeError):
                pass

        # Default: convert both to strings
        return str(actual), str(expected)

    # Operator implementations

    def _greater_than(self, actual: Any, expected: Any) -> bool:
        """Greater than operator (>)."""
        actual, expected = self._coerce_types(actual, expected)
        if actual is None:
            return False
        return actual > expected

    def _less_than(self, actual: Any, expected: Any) -> bool:
        """Less than operator (<)."""
        actual, expected = self._coerce_types(actual, expected)
        if actual is None:
            return False
        return actual < expected

    def _greater_equal(self, actual: Any, expected: Any) -> bool:
        """Greater than or equal operator (>=)."""
        actual, expected = self._coerce_types(actual, expected)
        if actual is None:
            return False
        return actual >= expected

    def _less_equal(self, actual: Any, expected: Any) -> bool:
        """Less than or equal operator (<=)."""
        actual, expected = self._coerce_types(actual, expected)
        if actual is None:
            return False
        return actual <= expected

    def _equal(self, actual: Any, expected: Any) -> bool:
        """Equal operator (==)."""
        actual, expected = self._coerce_types(actual, expected)
        return actual == expected

    def _not_equal(self, actual: Any, expected: Any) -> bool:
        """Not equal operator (!=)."""
        actual, expected = self._coerce_types(actual, expected)
        return actual != expected

    def _in_list(self, actual: Any, expected: Any) -> bool:
        """In list operator (in)."""
        if not isinstance(expected, list):
            logger.warning(f"'in' operator expects list, got {type(expected)}")
            return False
        return actual in expected

    def _not_in_list(self, actual: Any, expected: Any) -> bool:
        """Not in list operator (not_in)."""
        if not isinstance(expected, list):
            logger.warning(f"'not_in' operator expects list, got {type(expected)}")
            return False
        return actual not in expected

    def _format_violation_message(
        self, rule: ThresholdRule, actual_value: Any, device: str | None, data: dict[str, Any]
    ) -> str:
        """
        Format violation message using template or default.

        Args:
            rule: Threshold rule
            actual_value: Actual value found
            device: Device name
            data: Full data dict for additional context

        Returns:
            Formatted violation message
        """
        # Use custom message template if provided
        if rule.message:
            try:
                return rule.message.format(
                    field=rule.field,
                    value=rule.value,
                    actual=actual_value,
                    device=device or "unknown",
                    operator=rule.operator,
                    **data,  # Allow access to all data fields
                )
            except KeyError as e:
                logger.warning(f"Template field not found: {e}, using default message")

        # Default message format
        device_prefix = f"{device}: " if device else ""
        return (
            f"{device_prefix}{rule.field} is {actual_value} "
            f"(expected {rule.operator} {rule.value}) "
            f"[severity: {rule.severity}]"
        )


def generate_validation_report(results: list[DeviceValidationResult], format: str = "table") -> str:
    """
    Generate human-readable validation report.

    Args:
        results: List of device validation results
        format: Output format ('table', 'json', 'yaml')

    Returns:
        Formatted report string
    """
    if format == "json":
        import json

        return json.dumps(
            [
                {
                    "device": r.device,
                    "check": r.check_name,
                    "passed": r.passed,
                    "violations": r.violations,
                }
                for r in results
            ],
            indent=2,
        )

    if format == "yaml":
        import yaml

        return yaml.dump(
            [
                {
                    "device": r.device,
                    "check": r.check_name,
                    "passed": r.passed,
                    "violations": r.violations,
                }
                for r in results
            ],
            default_flow_style=False,
        )

    # table format (default)
    lines = []
    lines.append("=" * 80)
    lines.append("VALIDATION REPORT".center(80))
    lines.append("=" * 80)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    lines.append(f"\nSummary: {passed}/{total} passed, {failed} failed\n")

    for result in results:
        status = "✓ PASS" if result.passed else "✗ FAIL"
        lines.append(f"{status} | {result.device} | {result.check_name}")

        if not result.passed:
            for violation in result.violations:
                lines.append(f"  → {violation}")

    lines.append("=" * 80)

    return "\n".join(lines)
