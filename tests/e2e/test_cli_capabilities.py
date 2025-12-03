"""CLI-based E2E Tests for OLAV Agent Capabilities.

These tests use the CLI directly instead of the server API,
making them easier to run in development without full infrastructure.

Features:
    - Automatic timing and performance tracking
    - Test result caching (skip passed tests)
    - Performance logging to tests/e2e/logs/

Usage:
    # Run all CLI tests
    uv run pytest tests/e2e/test_cli_capabilities.py -v
    
    # Run with specific marker
    uv run pytest tests/e2e/test_cli_capabilities.py -m "not slow" -v
    
    # Force fresh run (disable cache)
    E2E_CACHE_DISABLED=true uv run pytest tests/e2e/test_cli_capabilities.py -v
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Import performance tracking
from tests.e2e.test_cache import get_current_tracker, perf_logger


# ============================================
# Configuration
# ============================================
PROJECT_ROOT = Path(__file__).parent.parent.parent
CLI_PATH = PROJECT_ROOT / "cli.py"
TIMEOUT_SIMPLE = 90   # Increased for free LLM APIs
TIMEOUT_COMPLEX = 180

# Performance thresholds (milliseconds)
PERF_THRESHOLD_SIMPLE = 60000   # 60s for simple queries (free LLM APIs are slow)
PERF_THRESHOLD_COMPLEX = 120000 # 120s for complex queries


def _check_cli_available() -> bool:
    """Check if CLI and dependencies are available."""
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(CLI_PATH), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT,
        )
        return result.returncode == 0
    except Exception:
        return False


# Skip all tests if CLI not available
pytestmark = pytest.mark.skipif(
    not _check_cli_available(),
    reason="CLI not available. Check dependencies with 'uv sync'."
)


# ============================================
# Data Classes
# ============================================
@dataclass
class CLIResult:
    """Result of a CLI execution."""
    query: str
    stdout: str
    stderr: str
    returncode: int
    duration_ms: float
    success: bool = field(init=False)
    
    def __post_init__(self):
        self.success = self.returncode == 0


@dataclass
class ValidationResult:
    """Result of response validation."""
    passed: bool
    score: float
    checks: dict[str, bool]
    details: str
    duration_ms: float = 0.0


# ============================================
# Helper Functions
# ============================================
def run_cli_query(
    query: str,
    mode: str = "standard",
    timeout: float = TIMEOUT_SIMPLE,
    yolo: bool = True,
) -> CLIResult:
    """Execute a query via CLI and return results.
    
    Args:
        query: The query text to execute
        mode: Query mode (standard/expert/inspection)
        timeout: Timeout in seconds
        yolo: Enable YOLO mode (auto-approve)
        
    Returns:
        CLIResult with output and metadata
    """
    start_time = time.time()
    
    # Log to performance tracker
    tracker = get_current_tracker()
    step_start = time.perf_counter()
    
    # Build command - use "query" subcommand
    cmd = ["uv", "run", "python", str(CLI_PATH), "query"]
    
    # Add mode flag
    if mode == "expert":
        cmd.extend(["-m", "expert"])
    elif mode == "inspection":
        cmd.extend(["-m", "inspection"])
    
    # Add query text
    cmd.append(query)
    
    # Set environment
    env = os.environ.copy()
    if yolo:
        env["OLAV_YOLO_MODE"] = "true"
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_ROOT,
            env=env,
        )
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Log step to performance tracker
        if tracker:
            tracker.metrics.log_step(
                f"cli_query_{mode}",
                duration_ms,
                {
                    "query": query[:100],  # Truncate for logging
                    "success": result.returncode == 0,
                    "output_size": len(result.stdout),
                }
            )
        
        # Also log to perf_logger
        perf_logger.info(
            f"CLI Query | Mode: {mode} | Duration: {duration_ms:.0f}ms | "
            f"Success: {result.returncode == 0} | Query: {query[:50]}"
        )
        
        return CLIResult(
            query=query,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        duration_ms = timeout * 1000
        if tracker:
            tracker.metrics.log_step(
                f"cli_query_{mode}_timeout",
                duration_ms,
                {"query": query[:100], "timeout": timeout}
            )
        perf_logger.warning(f"CLI Query TIMEOUT | {timeout}s | Query: {query[:50]}")
        
        return CLIResult(
            query=query,
            stdout="",
            stderr=f"Timeout after {timeout}s",
            returncode=-1,
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        perf_logger.error(f"CLI Query ERROR | {e} | Query: {query[:50]}")
        
        return CLIResult(
            query=query,
            stdout="",
            stderr=str(e),
            returncode=-1,
            duration_ms=(time.time() - start_time) * 1000,
        )


def validate_cli_response(
    result: CLIResult,
    must_contain: list[str] | None = None,
    must_not_contain: list[str] | None = None,
    min_length: int = 10,
) -> ValidationResult:
    """Validate a CLI response for quality.
    
    Args:
        result: The CLI result to validate
        must_contain: Strings that must appear in output
        must_not_contain: Strings that must NOT appear
        min_length: Minimum output length
        
    Returns:
        ValidationResult with pass/fail and details
    """
    checks = {}
    details = []
    
    # Combine stdout for checking
    output = result.stdout + result.stderr
    
    # Check 1: Command succeeded
    checks["success"] = result.success
    if not result.success:
        details.append(f"Command failed with code {result.returncode}")
    
    # Check 2: Output not empty
    checks["not_empty"] = len(output) >= min_length
    if not checks["not_empty"]:
        details.append(f"Output too short: {len(output)} < {min_length}")
    
    # Check 3: Contains required strings
    if must_contain:
        output_lower = output.lower()
        for term in must_contain:
            key = f"contains_{term}"
            checks[key] = term.lower() in output_lower
            if not checks[key]:
                details.append(f"Missing required term: '{term}'")
    
    # Check 4: Does not contain forbidden strings
    if must_not_contain:
        output_lower = output.lower()
        for term in must_not_contain:
            key = f"excludes_{term}"
            checks[key] = term.lower() not in output_lower
            if not checks[key]:
                details.append(f"Found forbidden term: '{term}'")
    
    # Check 5: No Python errors
    error_patterns = ["traceback", "error:", "exception:"]
    has_error = any(p in output.lower() for p in error_patterns)
    checks["no_errors"] = not has_error
    if has_error:
        details.append("Output contains error traces")
    
    # Calculate overall pass/score
    passed_checks = sum(1 for v in checks.values() if v)
    total_checks = len(checks)
    score = passed_checks / total_checks if total_checks > 0 else 0.0
    passed = all(checks.values())
    
    return ValidationResult(
        passed=passed,
        score=score,
        checks=checks,
        details="\n".join(details) if details else "All checks passed",
    )


# ============================================
# Category 1: Query Tests (Standard Mode)
# ============================================
class TestQueryCapabilities:
    """Tests for query capabilities via CLI."""
    
    def test_q01_bgp_status(self):
        """Q01: Test BGP status query."""
        result = run_cli_query("check R1 BGP status")
        
        validation = validate_cli_response(
            result,
            must_contain=["BGP"],
            min_length=20,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
        assert validation.passed, f"Validation failed: {validation.details}"
    
    def test_q02_interface_status(self):
        """Q02: Test interface status query."""
        result = run_cli_query("show interfaces on R1")
        
        validation = validate_cli_response(
            result,
            must_contain=["interface"],
            min_length=20,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
        assert validation.passed, f"Validation failed: {validation.details}"
    
    def test_q03_device_summary(self):
        """Q03: Test device summary query."""
        result = run_cli_query("summarize all devices")
        
        validation = validate_cli_response(
            result,
            must_contain=["device"],
            min_length=20,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
    
    def test_q04_route_table(self):
        """Q04: Test routing table query."""
        result = run_cli_query("show routing table of R1")
        
        validation = validate_cli_response(
            result,
            must_contain=["route"],
            min_length=20,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
    
    def test_q05_schema_discovery(self):
        """Q05: Test schema discovery."""
        result = run_cli_query("what tables are available?")
        
        validation = validate_cli_response(
            result,
            must_contain=["table"],
            min_length=30,
        )
        
        assert result.success, f"Query failed: {result.stderr}"


# ============================================
# Category 2: Expert Mode Tests
# ============================================
class TestExpertMode:
    """Tests for expert mode (deep dive) capabilities."""
    
    @pytest.mark.slow
    def test_d01_diagnosis(self):
        """D01: Test multi-step diagnosis."""
        result = run_cli_query(
            "analyze why R1 cannot reach R2",
            mode="expert",
            timeout=TIMEOUT_COMPLEX,
        )
        
        validation = validate_cli_response(
            result,
            must_contain=["R1", "R2"],
            min_length=50,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
    
    @pytest.mark.slow
    def test_d02_root_cause(self):
        """D02: Test root cause analysis."""
        result = run_cli_query(
            "why is BGP flapping on R1?",
            mode="expert",
            timeout=TIMEOUT_COMPLEX,
        )
        
        validation = validate_cli_response(
            result,
            must_contain=["BGP"],
            min_length=30,
        )
        
        assert result.success, f"Query failed: {result.stderr}"


# ============================================
# Category 3: Inspection Mode Tests
# ============================================
class TestInspectionMode:
    """Tests for inspection mode (batch audit) capabilities."""
    
    @pytest.mark.slow
    def test_i01_bgp_audit(self):
        """I01: Test BGP audit."""
        result = run_cli_query(
            "audit BGP on all devices",
            mode="inspection",
            timeout=TIMEOUT_COMPLEX,
        )
        
        validation = validate_cli_response(
            result,
            must_contain=["BGP"],
            min_length=30,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
    
    @pytest.mark.slow
    def test_i02_interface_audit(self):
        """I02: Test interface audit."""
        result = run_cli_query(
            "check interface status on all devices",
            mode="inspection",
            timeout=TIMEOUT_COMPLEX,
        )
        
        validation = validate_cli_response(
            result,
            must_contain=["interface"],
            min_length=30,
        )
        
        assert result.success, f"Query failed: {result.stderr}"


# ============================================
# Category 4: Error Handling Tests
# ============================================
class TestErrorHandling:
    """Tests for error handling and edge cases."""
    
    def test_x01_unknown_device(self):
        """X01: Handle unknown device gracefully."""
        result = run_cli_query("check BGP on NONEXISTENT_DEVICE_XYZ")
        
        # Should not crash, may return no data message
        output = result.stdout.lower()
        graceful_responses = ["no data", "not found", "unknown", "empty", "error"]
        has_graceful = any(r in output for r in graceful_responses)
        
        # Either succeeds with no data message or fails gracefully
        assert result.success or has_graceful, f"Should handle gracefully: {result.stderr}"
    
    def test_x02_empty_filter(self):
        """X02: Handle empty result gracefully."""
        result = run_cli_query("find BGP peers with ASN 99999")
        
        # Should succeed even with no results
        assert result.success, f"Query failed: {result.stderr}"
    
    def test_x03_chinese_query(self):
        """X03: Support Chinese language queries."""
        result = run_cli_query("查询 R1 的 BGP 状态")
        
        # Should understand Chinese
        validation = validate_cli_response(
            result,
            must_contain=["BGP"],
            min_length=20,
        )
        
        assert result.success, f"Chinese query failed: {result.stderr}"
    
    def test_x04_help_command(self):
        """X04: Show help correctly."""
        # Test the actual help via --help flag
        result = subprocess.run(
            ["uv", "run", "python", str(CLI_PATH), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT,
        )
        
        assert result.returncode == 0
        assert "OLAV" in result.stdout or "olav" in result.stdout.lower()


# ============================================
# Category 5: Schema-Aware Tests
# ============================================
class TestSchemaAware:
    """Tests for schema-aware query capabilities."""
    
    @pytest.mark.slow
    def test_s01_table_discovery(self):
        """S01: Discover available tables."""
        result = run_cli_query("what SuzieQ tables can I query?", timeout=TIMEOUT_COMPLEX)
        
        validation = validate_cli_response(
            result,
            must_contain=["table"],
            min_length=30,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
    
    @pytest.mark.slow
    def test_s02_field_discovery(self):
        """S02: Discover table fields."""
        result = run_cli_query("what fields are in the BGP table?", timeout=TIMEOUT_COMPLEX)
        
        validation = validate_cli_response(
            result,
            must_contain=["field"],
            min_length=30,
        )
        
        assert result.success, f"Query failed: {result.stderr}"
    
    @pytest.mark.slow
    def test_s03_method_discovery(self):
        """S03: Discover available methods."""
        result = run_cli_query("what methods can I use to query data?", timeout=TIMEOUT_COMPLEX)
        
        validation = validate_cli_response(
            result,
            must_contain=["method"],
            min_length=30,
        )
        
        assert result.success, f"Query failed: {result.stderr}"


# ============================================
# Report Generation
# ============================================
@pytest.fixture(scope="session", autouse=True)
def print_summary(request):
    """Print test summary after all tests."""
    yield
    
    print("\n" + "=" * 60)
    print("OLAV CLI E2E Test Summary")
    print("=" * 60)
    print("Categories:")
    print("  1. Query Capabilities (Standard Mode)")
    print("  2. Expert Mode (Deep Dive)")
    print("  3. Inspection Mode (Batch Audit)")
    print("  4. Error Handling")
    print("  5. Schema-Aware Queries")
    print("=" * 60)
    print("\nRun with '-m \"not slow\"' to skip long-running tests")
    print("=" * 60)
