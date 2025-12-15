"""Port availability detection for Windows/Linux/macOS.

This module provides utilities to check if a port is available,
find which process is using a port, and suggest alternative ports.

Usage:
    from olav.utils.port_check import check_port, check_ports, find_available_port

    # Check single port
    result = check_port(9200)
    if result.available:
        print("Port 9200 is available")
    else:
        print(f"Port 9200 in use by PID {result.pid} ({result.process_name})")

    # Check multiple ports
    results = check_ports([9200, 5432, 8080])
    for port, result in results.items():
        print(f"Port {port}: {'available' if result.available else 'in use'}")

    # Find alternative port
    alt_port = find_available_port(9200, max_attempts=10)
    print(f"Alternative port: {alt_port}")
"""

from __future__ import annotations

import logging
import platform
import socket
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)


@dataclass
class PortCheckResult:
    """Result of a port availability check."""

    port: int
    available: bool
    pid: int | None = None
    process_name: str | None = None
    error: str | None = None

    def __str__(self) -> str:
        if self.available:
            return f"Port {self.port}: ✅ Available"
        if self.pid:
            return f"Port {self.port}: ❌ In use by PID {self.pid} ({self.process_name or 'unknown'})"
        if self.error:
            return f"Port {self.port}: ⚠️ Check failed: {self.error}"
        return f"Port {self.port}: ❌ In use"


def check_port(port: int, host: str = "127.0.0.1") -> PortCheckResult:
    """Check if a port is available.

    Args:
        port: Port number to check
        host: Host to check (default: 127.0.0.1)

    Returns:
        PortCheckResult with availability status and process info if in use
    """
    # First, try socket connection (fastest method)
    if _is_port_available_socket(port, host):
        return PortCheckResult(port=port, available=True)

    # Port is in use, try to get process info
    pid, process_name = get_process_using_port(port)
    return PortCheckResult(
        port=port,
        available=False,
        pid=pid,
        process_name=process_name,
    )


def check_ports(ports: list[int], host: str = "127.0.0.1") -> Mapping[int, PortCheckResult]:
    """Check multiple ports for availability.

    Args:
        ports: List of port numbers to check
        host: Host to check (default: 127.0.0.1)

    Returns:
        Dict mapping port number to PortCheckResult
    """
    return {port: check_port(port, host) for port in ports}


def find_available_port(
    preferred_port: int,
    max_attempts: int = 10,
    host: str = "127.0.0.1",
) -> int | None:
    """Find an available port starting from preferred_port.

    Args:
        preferred_port: Preferred port to start searching from
        max_attempts: Maximum number of ports to try
        host: Host to check (default: 127.0.0.1)

    Returns:
        Available port number, or None if none found
    """
    for i in range(max_attempts):
        port = preferred_port + i
        if _is_port_available_socket(port, host):
            return port
    return None


def get_process_using_port(port: int) -> tuple[int | None, str | None]:
    """Get the process using a specific port.

    Args:
        port: Port number to check

    Returns:
        Tuple of (PID, process_name), or (None, None) if not found
    """
    system = platform.system().lower()

    if system == "windows":
        return _get_process_windows(port)
    elif system in ("linux", "darwin"):
        return _get_process_unix(port)
    else:
        logger.warning(f"Unsupported platform: {system}")
        return None, None


def _is_port_available_socket(port: int, host: str = "127.0.0.1") -> bool:
    """Check port availability using socket connection.

    This is the fastest method but doesn't provide process info.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            # If connect_ex returns non-zero, port is not listening
            return result != 0
    except OSError:
        return True  # Assume available if socket error


def _get_process_windows(port: int) -> tuple[int | None, str | None]:
    """Get process info on Windows using netstat and tasklist.

    Uses:
        netstat -ano | findstr :<port>
        tasklist /FI "PID eq <pid>"
    """
    try:
        # Find PID using netstat
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            return None, None

        # Parse netstat output
        pid = None
        for line in result.stdout.splitlines():
            if f":{port}" in line and ("LISTENING" in line or "ESTABLISHED" in line):
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        pid = int(parts[-1])
                        break
                    except ValueError:
                        continue

        if not pid:
            return None, None

        # Get process name using tasklist
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip():
            # Parse CSV format: "process.exe","PID","Session","Session#","Memory"
            parts = result.stdout.strip().split(",")
            if parts:
                process_name = parts[0].strip('"')
                return pid, process_name

        return pid, None

    except subprocess.TimeoutExpired:
        logger.warning("Timeout getting process info on Windows")
        return None, None
    except Exception as e:
        logger.warning(f"Error getting process info on Windows: {e}")
        return None, None


def _get_process_unix(port: int) -> tuple[int | None, str | None]:
    """Get process info on Linux/macOS.

    Uses:
        Linux: ss -tlnp | grep :<port>
        macOS: lsof -i :<port>
    """
    system = platform.system().lower()

    try:
        if system == "linux":
            return _get_process_linux_ss(port)
        else:  # macOS
            return _get_process_macos_lsof(port)
    except Exception as e:
        logger.warning(f"Error getting process info on {system}: {e}")
        return None, None


def _get_process_linux_ss(port: int) -> tuple[int | None, str | None]:
    """Get process info on Linux using ss command."""
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            # Fallback to lsof if ss is not available
            return _get_process_lsof(port)

        for line in result.stdout.splitlines():
            if f":{port}" in line:
                # Parse ss output: ... users:(("nginx",pid=1234,fd=5))
                if "users:" in line:
                    import re
                    match = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
                    if match:
                        return int(match.group(2)), match.group(1)

        return None, None

    except FileNotFoundError:
        # ss not available, try lsof
        return _get_process_lsof(port)
    except subprocess.TimeoutExpired:
        logger.warning("Timeout getting process info on Linux")
        return None, None


def _get_process_macos_lsof(port: int) -> tuple[int | None, str | None]:
    """Get process info on macOS using lsof command."""
    return _get_process_lsof(port)


def _get_process_lsof(port: int) -> tuple[int | None, str | None]:
    """Get process info using lsof (works on Linux and macOS)."""
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-P", "-n"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            return None, None

        # Parse lsof output
        # COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 2:  # Skip header
            parts = lines[1].split()
            if len(parts) >= 2:
                process_name = parts[0]
                pid = int(parts[1])
                return pid, process_name

        return None, None

    except FileNotFoundError:
        logger.warning("lsof not found")
        return None, None
    except subprocess.TimeoutExpired:
        logger.warning("Timeout running lsof")
        return None, None


# Default ports used by OLAV services
OLAV_DEFAULT_PORTS = {
    "opensearch": 9200,
    "postgres": 5432,
    "netbox": 8080,
    "olav_api": 8000,
    "suzieq": 8501,
    "fluent_bit_syslog": 514,
    "fluent_bit_http": 2020,
}

# Alternative ports for common conflicts
OLAV_ALTERNATIVE_PORTS = {
    9200: 19200,   # OpenSearch (avoid Elasticsearch conflict)
    5432: 15432,   # PostgreSQL (avoid existing PostgreSQL)
    8080: 8081,    # NetBox (common web port)
    8000: 8001,    # OLAV API
    8501: 8502,    # SuzieQ (Streamlit)
    514: 1514,     # Syslog (requires root for <1024)
}


def check_olav_ports() -> dict[str, PortCheckResult]:
    """Check all default OLAV ports.

    Returns:
        Dict mapping service name to PortCheckResult
    """
    results = {}
    for service, port in OLAV_DEFAULT_PORTS.items():
        results[service] = check_port(port)
    return results


def suggest_alternative_port(port: int) -> int:
    """Suggest an alternative port for a conflicting port.

    Args:
        port: Original port that has a conflict

    Returns:
        Suggested alternative port
    """
    if port in OLAV_ALTERNATIVE_PORTS:
        alt_port = OLAV_ALTERNATIVE_PORTS[port]
        if check_port(alt_port).available:
            return alt_port
    
    # Find next available port
    alt = find_available_port(port + 1, max_attempts=100)
    return alt if alt else port + 1


if __name__ == "__main__":
    # Quick test
    import sys

    ports_to_check = [9200, 5432, 8080, 8000]
    if len(sys.argv) > 1:
        ports_to_check = [int(p) for p in sys.argv[1:]]

    print("OLAV Port Availability Check")
    print("=" * 40)

    for port in ports_to_check:
        result = check_port(port)
        print(result)

        if not result.available:
            alt = suggest_alternative_port(port)
            print(f"  → Suggested alternative: {alt}")

    print()
    print("All OLAV default ports:")
    print("-" * 40)
    for service, result in check_olav_ports().items():
        print(f"  {service:20} (:{result.port}): {'✅' if result.available else '❌'}")
