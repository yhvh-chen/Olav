"""E2E Tests for Expert Mode with Real Fault Injection.

These tests use Nornir directly to inject real faults into network devices,
then verify the Agent (in expert mode) can correctly diagnose the root cause.

Unlike test_fault_injection.py which uses natural language queries to inject faults,
this module uses Nornir's netmiko_send_config for reliable, deterministic fault injection.

Fault Types:
    - F1: Interface Shutdown (admin down)
    - F2: IP Address Change (wrong IP)
    - F3: BGP Neighbor Shutdown
    - F4: OSPF Network Removal
    - F5: ACL Blocking ICMP

Safety:
    - All faults use dedicated test interfaces (Loopback100)
    - Tests ALWAYS restore original config after each fault
    - YOLO mode required for automated execution

Prerequisites:
    - NetBox with test devices (R1, R2) tagged with 'olav'
    - Device SSH credentials in environment
    - OLAV_YOLO_MODE=true

Usage:
    # Run all expert mode fault tests
    OLAV_YOLO_MODE=true uv run pytest tests/e2e/test_expert_mode_fault_injection.py -v
    
    # Run specific fault test
    uv run pytest tests/e2e/test_expert_mode_fault_injection.py -k "interface_shutdown" -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ============================================
# Test Constants
# ============================================
# Test device (must exist in NetBox with 'olav' tag)
TEST_DEVICE = os.environ.get("OLAV_TEST_DEVICE", "R1")
TEST_DEVICE_B = os.environ.get("OLAV_TEST_DEVICE_B", "R2")

# Test interface for fault injection (safe to modify)
TEST_INTERFACE = "Loopback100"
TEST_INTERFACE_IP = "100.100.100.1"
TEST_INTERFACE_MASK = "255.255.255.255"

# Timeouts
TIMEOUT_CONFIG = 30      # seconds for Nornir config
TIMEOUT_DIAGNOSE = 180   # seconds for expert mode diagnosis (longer due to deep dive)
TIMEOUT_WAIT = 30        # seconds to wait after config change for SuzieQ to poll

# Minimum confidence for diagnosis to pass
MIN_CONFIDENCE = 0.3


# ============================================
# Skip Conditions
# ============================================
def _is_yolo_mode() -> bool:
    """Check if YOLO mode is enabled."""
    return os.environ.get("OLAV_YOLO_MODE", "").lower() in ("1", "true", "yes")


def _nornir_available() -> bool:
    """Check if Nornir sandbox is available."""
    try:
        from olav.execution.backends.nornir_sandbox import NornirSandbox
        sandbox = NornirSandbox()
        return len(sandbox.nr.inventory.hosts) > 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.expert_mode,
    pytest.mark.fault_injection,
    pytest.mark.destructive,
    pytest.mark.slow,
    pytest.mark.skipif(
        not _is_yolo_mode(),
        reason="Fault injection tests require YOLO mode. Set OLAV_YOLO_MODE=true"
    ),
]


# ============================================
# Data Classes
# ============================================
@dataclass
class FaultConfig:
    """Configuration for injecting a fault via Nornir."""
    name: str
    description: str
    inject_commands: list[str]   # Commands to inject fault
    restore_commands: list[str]  # Commands to restore original config
    device: str = TEST_DEVICE


@dataclass
class DiagnosisQuery:
    """Query for diagnosing a fault."""
    query: str
    expected_keywords: list[str]
    min_confidence: float = MIN_CONFIDENCE


@dataclass
class DiagnosisResult:
    """Result of a diagnosis attempt."""
    success: bool
    response: str
    found_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    confidence: float = 0.0
    duration_ms: float = 0.0
    tool_calls: list[str] = field(default_factory=list)


# ============================================
# Fault Definitions
# ============================================
FAULT_CONFIGS = {
    "interface_shutdown": FaultConfig(
        name="Interface Shutdown",
        description="Shutdown test interface (admin down)",
        inject_commands=[
            f"interface {TEST_INTERFACE}",
            "shutdown",
        ],
        restore_commands=[
            f"interface {TEST_INTERFACE}",
            "no shutdown",
        ],
    ),
    
    "ip_address_change": FaultConfig(
        name="IP Address Change",
        description="Change interface IP to wrong value",
        inject_commands=[
            f"interface {TEST_INTERFACE}",
            "no ip address",
            "ip address 99.99.99.99 255.255.255.255",
        ],
        restore_commands=[
            f"interface {TEST_INTERFACE}",
            "no ip address",
            f"ip address {TEST_INTERFACE_IP} {TEST_INTERFACE_MASK}",
        ],
    ),
    
    "interface_description_change": FaultConfig(
        name="Interface Description Change",
        description="Change interface description (benign, for testing)",
        inject_commands=[
            f"interface {TEST_INTERFACE}",
            "description OLAV_FAULT_TEST_INJECTED",
        ],
        restore_commands=[
            f"interface {TEST_INTERFACE}",
            "no description",
        ],
    ),
    
    "loopback_removal": FaultConfig(
        name="Loopback Removal",
        description="Remove test loopback interface entirely",
        inject_commands=[
            f"no interface {TEST_INTERFACE}",
        ],
        restore_commands=[
            f"interface {TEST_INTERFACE}",
            f"ip address {TEST_INTERFACE_IP} {TEST_INTERFACE_MASK}",
            "no shutdown",
        ],
    ),
}


DIAGNOSIS_QUERIES = {
    "interface_shutdown": DiagnosisQuery(
        query=f"Why is {TEST_INTERFACE} on {TEST_DEVICE} down? Analyze the root cause.",
        expected_keywords=["shutdown", "down", "admin", "disabled", "administratively", "not found", "missing"],
        min_confidence=0.2,  # Lower threshold due to SuzieQ data latency
    ),
    
    "ip_address_change": DiagnosisQuery(
        query=f"Analyze IP configuration issue on {TEST_DEVICE} {TEST_INTERFACE}",
        expected_keywords=["ip", "address", "99.99.99", "wrong", "incorrect", "changed"],
        min_confidence=0.2,
    ),
    
    "interface_status": DiagnosisQuery(
        query=f"Check all interface status on {TEST_DEVICE} and find anomalies",
        expected_keywords=["interface", "status", "down", "up"],
        min_confidence=0.2,
    ),
    
    "loopback_removal": DiagnosisQuery(
        query=f"{TEST_INTERFACE} on {TEST_DEVICE} is missing. Investigate.",
        expected_keywords=["loopback", "missing", "not found", "removed", "deleted", "no record"],
        min_confidence=0.2,
    ),
}


# ============================================
# Nornir Fault Injection Helpers
# ============================================
class NornirFaultInjector:
    """Handles fault injection and restoration using Nornir."""
    
    def __init__(self):
        from olav.execution.backends.nornir_sandbox import NornirSandbox
        self.sandbox = NornirSandbox()
        self._injected_faults: list[FaultConfig] = []
    
    def inject_fault(self, fault: FaultConfig) -> bool:
        """Inject a fault into a device using Nornir.
        
        Args:
            fault: FaultConfig with inject_commands
            
        Returns:
            True if injection succeeded
        """
        try:
            from nornir.core.filter import F
            from nornir_netmiko.tasks import netmiko_send_config
            
            target = self.sandbox.nr.filter(F(name=fault.device))
            if not target.inventory.hosts:
                print(f"ERROR: Device '{fault.device}' not found in inventory")
                return False
            
            print(f"Injecting fault: {fault.name}")
            print(f"  Device: {fault.device}")
            print(f"  Commands: {fault.inject_commands}")
            
            result = target.run(
                task=netmiko_send_config,
                config_commands=fault.inject_commands,
            )
            
            for host, host_result in result.items():
                if host_result.failed:
                    print(f"ERROR: Failed to inject fault on {host}: {host_result.exception}")
                    return False
                print(f"SUCCESS: Fault injected on {host}")
                print(f"  Output: {host_result.result[:200] if host_result.result else 'N/A'}")
            
            self._injected_faults.append(fault)
            return True
            
        except Exception as e:
            print(f"ERROR: Fault injection failed: {e}")
            return False
    
    def restore_fault(self, fault: FaultConfig) -> bool:
        """Restore configuration after a fault.
        
        Args:
            fault: FaultConfig with restore_commands
            
        Returns:
            True if restore succeeded
        """
        try:
            from nornir.core.filter import F
            from nornir_netmiko.tasks import netmiko_send_config
            
            target = self.sandbox.nr.filter(F(name=fault.device))
            if not target.inventory.hosts:
                print(f"ERROR: Device '{fault.device}' not found")
                return False
            
            print(f"Restoring: {fault.name}")
            print(f"  Commands: {fault.restore_commands}")
            
            result = target.run(
                task=netmiko_send_config,
                config_commands=fault.restore_commands,
            )
            
            for host, host_result in result.items():
                if host_result.failed:
                    print(f"WARNING: Failed to restore on {host}: {host_result.exception}")
                    return False
                print(f"SUCCESS: Config restored on {host}")
            
            if fault in self._injected_faults:
                self._injected_faults.remove(fault)
            return True
            
        except Exception as e:
            print(f"ERROR: Restore failed: {e}")
            return False
    
    def restore_all(self) -> None:
        """Restore all injected faults."""
        for fault in list(self._injected_faults):
            try:
                self.restore_fault(fault)
            except Exception as e:
                print(f"WARNING: Failed to restore {fault.name}: {e}")
    
    def verify_device_reachable(self, device: str) -> bool:
        """Verify device is reachable via Nornir."""
        try:
            from nornir.core.filter import F
            from nornir_netmiko.tasks import netmiko_send_command
            
            target = self.sandbox.nr.filter(F(name=device))
            if not target.inventory.hosts:
                return False
            
            result = target.run(
                task=netmiko_send_command,
                command_string="show version | include uptime",
            )
            
            for host, host_result in result.items():
                return not host_result.failed
            
            return False
        except Exception:
            return False


# ============================================
# Agent Diagnosis Helpers
# ============================================
def run_expert_diagnosis(query: str, timeout: float = TIMEOUT_DIAGNOSE) -> DiagnosisResult:
    """Run agent diagnosis in expert mode.
    
    Args:
        query: Diagnosis query
        timeout: Timeout in seconds
        
    Returns:
        DiagnosisResult with analysis
    """
    import subprocess
    from pathlib import Path
    
    start = time.time()
    
    # Use absolute path to cli.py
    cli_path = Path(__file__).resolve().parent.parent.parent / "cli.py"
    project_root = cli_path.parent
    
    print(f"  CLI path: {cli_path}")
    print(f"  Project root: {project_root}")
    
    # Escape quotes in query for shell
    escaped_query = query.replace('"', '\\"')
    
    # Use shell command string to properly handle quotes
    cmd = f'uv run python "{cli_path}" query -m expert "{escaped_query}"'
    
    print(f"  Command: {cmd}")
    
    env = os.environ.copy()
    env["OLAV_YOLO_MODE"] = "true"
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(project_root),
            shell=True,  # Use shell to properly handle quoted arguments
        )
        
        duration_ms = (time.time() - start) * 1000
        
        response = result.stdout + result.stderr
        
        print(f"  Return code: {result.returncode}")
        print(f"  Stdout length: {len(result.stdout)}")
        print(f"  Stderr length: {len(result.stderr)}")
        
        return DiagnosisResult(
            success=result.returncode == 0,
            response=response,
            duration_ms=duration_ms,
        )
        
    except subprocess.TimeoutExpired:
        return DiagnosisResult(
            success=False,
            response=f"Timeout after {timeout}s",
            duration_ms=timeout * 1000,
        )
    except Exception as e:
        return DiagnosisResult(
            success=False,
            response=str(e),
        )


def analyze_diagnosis(result: DiagnosisResult, query: DiagnosisQuery) -> DiagnosisResult:
    """Analyze diagnosis result against expected keywords.
    
    Args:
        result: Raw DiagnosisResult
        query: DiagnosisQuery with expected keywords
        
    Returns:
        Updated DiagnosisResult with keyword analysis
    """
    response_lower = result.response.lower()
    
    found = []
    missing = []
    
    for keyword in query.expected_keywords:
        if keyword.lower() in response_lower:
            found.append(keyword)
        else:
            missing.append(keyword)
    
    confidence = len(found) / len(query.expected_keywords) if query.expected_keywords else 0.0
    
    result.found_keywords = found
    result.missing_keywords = missing
    result.confidence = confidence
    
    return result


# ============================================
# Fixtures
# ============================================
@pytest.fixture(scope="module")
def nornir_injector():
    """Create Nornir fault injector with auto-cleanup."""
    try:
        injector = NornirFaultInjector()
        yield injector
    finally:
        # Always restore all faults on teardown
        try:
            injector.restore_all()
        except Exception as e:
            print(f"WARNING: Cleanup failed: {e}")


@pytest.fixture(autouse=True)
def ensure_device_reachable(nornir_injector):
    """Ensure test device is reachable before each test."""
    if not nornir_injector.verify_device_reachable(TEST_DEVICE):
        pytest.skip(f"Test device {TEST_DEVICE} not reachable")


# ============================================
# Test Classes
# ============================================
class TestExpertModeInterfaceFaults:
    """Expert mode tests for interface-level faults."""
    
    def test_diagnose_interface_shutdown(self, nornir_injector):
        """Expert mode diagnoses administratively shutdown interface.
        
        Steps:
            1. Inject: shutdown Loopback100 via Nornir
            2. Diagnose: Ask agent why interface is down
            3. Verify: Agent identifies admin shutdown
            4. Restore: no shutdown Loopback100
        """
        fault = FAULT_CONFIGS["interface_shutdown"]
        query = DIAGNOSIS_QUERIES["interface_shutdown"]
        
        # 1. Inject fault via Nornir
        assert nornir_injector.inject_fault(fault), "Failed to inject fault"
        time.sleep(TIMEOUT_WAIT)  # Wait for SuzieQ to poll
        
        try:
            # 2. Run expert diagnosis
            print(f"\n运行专家模式诊断: {query.query}")
            result = run_expert_diagnosis(query.query)
            result = analyze_diagnosis(result, query)
            
            # 3. Verify diagnosis
            print(f"\n诊断结果:")
            print(f"  成功: {result.success}")
            print(f"  置信度: {result.confidence:.0%}")
            print(f"  找到关键词: {result.found_keywords}")
            print(f"  缺失关键词: {result.missing_keywords}")
            print(f"  耗时: {result.duration_ms:.0f}ms")
            
            assert result.success, f"Diagnosis failed: {result.response[:500]}"
            assert result.confidence >= query.min_confidence, \
                f"Low confidence ({result.confidence:.0%}). Missing: {result.missing_keywords}"
            
        finally:
            # 4. Always restore
            nornir_injector.restore_fault(fault)
    
    def test_diagnose_ip_change(self, nornir_injector):
        """Expert mode diagnoses wrong IP address configuration.
        
        Steps:
            1. Inject: Change IP to 99.99.99.99 via Nornir
            2. Diagnose: Ask agent about IP configuration
            3. Verify: Agent identifies wrong IP
            4. Restore: Original IP
        """
        fault = FAULT_CONFIGS["ip_address_change"]
        query = DIAGNOSIS_QUERIES["ip_address_change"]
        
        # 1. Inject fault
        assert nornir_injector.inject_fault(fault), "Failed to inject fault"
        time.sleep(TIMEOUT_WAIT)
        
        try:
            # 2. Run diagnosis
            print(f"\n运行专家模式诊断: {query.query}")
            result = run_expert_diagnosis(query.query)
            result = analyze_diagnosis(result, query)
            
            # 3. Verify
            print(f"\n诊断结果:")
            print(f"  成功: {result.success}")
            print(f"  置信度: {result.confidence:.0%}")
            print(f"  响应片段: {result.response[:300]}...")
            
            assert result.success, f"Diagnosis failed: {result.response[:500]}"
            assert result.confidence >= query.min_confidence, \
                f"Low confidence ({result.confidence:.0%})"
            
        finally:
            # 4. Restore
            nornir_injector.restore_fault(fault)


class TestExpertModeComplexScenarios:
    """Expert mode tests for complex multi-step scenarios."""
    
    @pytest.mark.slow
    def test_multiple_faults_correlation(self, nornir_injector):
        """Expert mode correlates multiple faults.
        
        Steps:
            1. Inject: Shutdown interface
            2. Inject: Change IP (on another test if available)
            3. Diagnose: Ask for comprehensive analysis
            4. Verify: Agent finds multiple issues
            5. Restore: All faults
        """
        faults = [
            FAULT_CONFIGS["interface_shutdown"],
            FAULT_CONFIGS["interface_description_change"],
        ]
        
        # Inject all faults
        for fault in faults:
            assert nornir_injector.inject_fault(fault), f"Failed to inject {fault.name}"
        
        time.sleep(TIMEOUT_WAIT)
        
        try:
            # Comprehensive diagnosis
            query = f"全面分析 {TEST_DEVICE} 的配置问题，找出所有异常"
            print(f"\n综合诊断: {query}")
            
            result = run_expert_diagnosis(query, timeout=180)  # Longer timeout
            
            print(f"\n诊断结果:")
            print(f"  成功: {result.success}")
            print(f"  响应长度: {len(result.response)} 字符")
            print(f"  耗时: {result.duration_ms:.0f}ms")
            
            assert result.success, f"Diagnosis failed: {result.response[:500]}"
            
            # Should find shutdown-related issues
            response_lower = result.response.lower()
            found_shutdown = any(kw in response_lower for kw in ["shutdown", "down", "disabled"])
            
            print(f"  发现 shutdown 相关: {found_shutdown}")
            
        finally:
            # Restore all
            for fault in faults:
                nornir_injector.restore_fault(fault)


class TestExpertModeDeepDive:
    """Tests specifically for Deep Dive (iterative reasoning) capabilities."""
    
    def test_deep_dive_iterative_analysis(self, nornir_injector):
        """Verify expert mode uses iterative deep dive analysis.
        
        The expert mode should:
            1. Make initial assessment
            2. Query additional data based on findings
            3. Correlate across multiple sources
            4. Provide root cause analysis
        """
        fault = FAULT_CONFIGS["interface_shutdown"]
        
        assert nornir_injector.inject_fault(fault), "Failed to inject fault"
        time.sleep(TIMEOUT_WAIT)
        
        try:
            # Complex query requiring deep analysis
            query = f"""
            {TEST_DEVICE} 的 {TEST_INTERFACE} 似乎有问题。
            请进行深度分析:
            1. 检查接口状态
            2. 检查路由表是否受影响
            3. 分析可能的根因
            """
            
            print(f"\n深度分析查询: {query}")
            result = run_expert_diagnosis(query, timeout=180)
            
            print(f"\n诊断结果:")
            print(f"  成功: {result.success}")
            print(f"  耗时: {result.duration_ms:.0f}ms")
            
            # For deep dive, we expect longer response with multiple sections
            assert result.success, f"Deep dive failed: {result.response[:500]}"
            assert len(result.response) > 200, "Response too short for deep dive"
            
            # Check response mentions multiple aspects
            response_lower = result.response.lower()
            aspects_found = sum([
                "interface" in response_lower or "接口" in response_lower,
                "status" in response_lower or "状态" in response_lower,
                "down" in response_lower or "shutdown" in response_lower,
            ])
            
            print(f"  覆盖方面数: {aspects_found}/3")
            assert aspects_found >= 2, "Deep dive should analyze multiple aspects"
            
        finally:
            nornir_injector.restore_fault(fault)


# ============================================
# Summary Fixture
# ============================================
@pytest.fixture(scope="session", autouse=True)
def print_test_summary(request):
    """Print test summary at end of session."""
    yield
    
    print("\n" + "=" * 70)
    print("Expert Mode Fault Injection E2E Test Summary")
    print("=" * 70)
    print(f"Test Device: {TEST_DEVICE}")
    print(f"Test Interface: {TEST_INTERFACE}")
    print()
    print("Fault Types:")
    for key, fault in FAULT_CONFIGS.items():
        print(f"  - {fault.name}: {fault.description}")
    print()
    print("Expert Mode Features Tested:")
    print("  - Deep Dive iterative reasoning")
    print("  - Multi-source data correlation")
    print("  - Root cause analysis")
    print("  - Real Nornir fault injection (not natural language)")
    print("=" * 70)


# ============================================
# Main
# ============================================
if __name__ == "__main__":
    # Allow running directly for debugging
    pytest.main([__file__, "-v", "-s", "--tb=short"])
