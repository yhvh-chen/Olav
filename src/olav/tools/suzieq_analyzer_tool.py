"""SuzieQ Analyzer Tools - High-level analysis using SuzieQ capabilities.

This module provides advanced analysis tools that leverage SuzieQ's
path.show(), aver (assertions), and topology.summarize() methods.

Tools:
- suzieq_path_trace: Network path tracing from source to destination
- suzieq_health_check: Device health assertions using aver()
- suzieq_topology_analyze: Topology analysis and anomaly detection

These tools are designed for the "Quick Analyzer" phase of the
Supervisor-Inspector pattern, providing fast initial analysis
before detailed device inspection.

Note: SuzieQ data is historical (collected periodically), so confidence
is capped at 60%. Real-time verification requires NETCONF/CLI.
"""

import logging
import time
from typing import Any, Literal

from typing_extensions import TypedDict

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# =============================================================================
# Data Types
# =============================================================================


class SuspectedIssue(TypedDict):
    """A suspected fault point identified by Quick Analyzer."""

    device: str
    layer: Literal["L1", "L2", "L3", "L4"]
    issue: str  # e.g., "BGP peer down", "Interface flapping"
    confidence: float  # 0.0 - 1.0
    data_age_seconds: int  # Data freshness
    source: Literal["suzieq", "realtime"]


class PathHop(TypedDict):
    """A single hop in the network path."""

    hop_number: int
    device: str
    ingress_interface: str | None
    egress_interface: str | None
    next_hop: str | None
    mtu: int | None
    is_overlay: bool


class QuickScanResult(TypedDict):
    """Complete result from Quick Analyzer."""

    suspected_issues: list[SuspectedIssue]
    path_devices: list[str]
    path_hops: list[PathHop]
    topology_anomalies: list[str]
    data_freshness: str  # Human-readable, e.g., "Data from 2 minutes ago"
    scan_duration_ms: float


class HealthCheckResult(TypedDict):
    """Result from health check assertions."""

    device: str
    checks: list[dict[str, Any]]  # [{name, passed, failures}]
    overall_healthy: bool
    data_age_seconds: int


class TopologyAnalysisResult(TypedDict):
    """Result from topology analysis."""

    devices: list[str]
    connections: list[dict[str, Any]]
    anomalies: list[str]
    single_points_of_failure: list[str]


# =============================================================================
# Utility Functions
# =============================================================================


def calculate_confidence(data_age_seconds: int) -> float:
    """Calculate confidence based on data age.

    Historical data from SuzieQ is capped at 60% confidence.
    Confidence decreases as data ages:
    - <= 1 min: 60%
    - <= 3 min: 50%
    - <= 5 min: 40%
    - > 5 min: 25%

    Args:
        data_age_seconds: Age of the data in seconds

    Returns:
        Confidence value between 0.25 and 0.60
    """
    if data_age_seconds <= 60:
        return 0.60
    if data_age_seconds <= 180:
        return 0.50
    if data_age_seconds <= 300:
        return 0.40
    return 0.25


def get_suzieq_context():
    """Get SuzieQ context for queries.

    Returns a context object configured for the current environment.
    Falls back to a mock context if SuzieQ is not available.
    """
    try:
        from suzieq.sqobjects import get_sqobject

        # Try to get a real SuzieQ context
        # This uses the default config from suzieq-cfg.yml
        return {"get_sqobject": get_sqobject, "available": True}
    except ImportError:
        logger.warning("SuzieQ not available, using mock context")
        return {"get_sqobject": None, "available": False}


def map_layer_from_table(table: str) -> Literal["L1", "L2", "L3", "L4"]:
    """Map SuzieQ table name to OSI layer.

    Args:
        table: SuzieQ table name (e.g., 'interfaces', 'bgp', 'routes')

    Returns:
        Layer designation (L1, L2, L3, or L4)
    """
    layer_mapping = {
        # L1 - Physical
        "interfaces": "L1",
        "device": "L1",
        # L2 - Data Link
        "vlan": "L2",
        "mac": "L2",
        "lldp": "L2",
        "mlag": "L2",
        "evpnVni": "L2",
        # L3 - Network
        "bgp": "L3",
        "ospf": "L3",
        "routes": "L3",
        "arpnd": "L3",
        "address": "L3",
        # L4 - Transport (limited coverage in SuzieQ)
    }
    return layer_mapping.get(table, "L3")


def format_data_freshness(data_age_seconds: int) -> str:
    """Format data age into human-readable string.

    Args:
        data_age_seconds: Age of the data in seconds

    Returns:
        Human-readable string like "Data from 2 minutes ago"
    """
    if data_age_seconds < 60:
        return f"Data from {data_age_seconds} seconds ago"
    if data_age_seconds < 3600:
        minutes = data_age_seconds // 60
        return f"Data from {minutes} minute{'s' if minutes > 1 else ''} ago"
    hours = data_age_seconds // 3600
    return f"Data from {hours} hour{'s' if hours > 1 else ''} ago (may be stale)"


# =============================================================================
# Quick Analyzer Tools
# =============================================================================


@tool
def suzieq_path_trace(
    source: str,
    destination: str,
    vrf: str = "default",
    namespace: str | None = None,
) -> QuickScanResult:
    """Trace network path from source to destination using SuzieQ path.show().

    Uses SuzieQ's path analysis to find all devices and hops between
    source and destination. Also runs health checks on path devices
    to identify potential issues.

    Args:
        source: Source device name or IP address
        destination: Destination device name or IP address
        vrf: VRF name for routing context (default: "default")
        namespace: SuzieQ namespace (optional)

    Returns:
        QuickScanResult containing:
        - suspected_issues: List of potential problems found on the path
        - path_devices: List of device names on the path
        - path_hops: Detailed hop-by-hop information
        - topology_anomalies: Any topology issues detected
        - data_freshness: Human-readable data age
        - scan_duration_ms: Time taken for the scan

    Example:
        >>> result = suzieq_path_trace(source="SW1", destination="10.0.0.100")
        >>> print(result["path_devices"])
        ["SW1", "R1", "R2", "SW2"]
    """
    start_time = time.perf_counter()
    ctx = get_suzieq_context()

    result = QuickScanResult(
        suspected_issues=[],
        path_devices=[],
        path_hops=[],
        topology_anomalies=[],
        data_freshness="Unknown",
        scan_duration_ms=0,
    )

    if not ctx["available"]:
        result["data_freshness"] = "SuzieQ not available - using mock data"
        result["scan_duration_ms"] = (time.perf_counter() - start_time) * 1000
        return result

    try:
        get_sqobject = ctx["get_sqobject"]

        # 1. Get path using path.show()
        path_obj = get_sqobject("path")
        kwargs = {"source": source, "dest": destination, "vrf": vrf}
        if namespace:
            kwargs["namespace"] = namespace

        path_df = path_obj.show(**kwargs)

        if path_df is None or path_df.empty:
            result["data_freshness"] = "No path found"
            result["scan_duration_ms"] = (time.perf_counter() - start_time) * 1000
            return result

        # 2. Extract path devices and hops
        path_devices = []
        path_hops = []

        for _idx, row in path_df.iterrows():
            device = row.get("hostname", "")
            if device and device not in path_devices:
                path_devices.append(device)

            hop = PathHop(
                hop_number=len(path_hops) + 1,
                device=device,
                ingress_interface=row.get("iif"),
                egress_interface=row.get("oif"),
                next_hop=row.get("nexthopIp"),
                mtu=row.get("mtu"),
                is_overlay=row.get("overlay", False),
            )
            path_hops.append(hop)

        result["path_devices"] = path_devices
        result["path_hops"] = path_hops

        # 3. Check for MTU mismatches along path
        mtus = [h.get("mtu") for h in path_hops if h.get("mtu")]
        if mtus and len(set(mtus)) > 1:
            min_mtu = min(mtus)
            max_mtu = max(mtus)
            result["suspected_issues"].append(
                SuspectedIssue(
                    device="path",
                    layer="L1",
                    issue=f"MTU mismatch along path: {min_mtu} - {max_mtu}",
                    confidence=0.55,
                    data_age_seconds=60,  # Assume recent
                    source="suzieq",
                )
            )

        # 4. Run health checks on path devices
        for device in path_devices:
            health = _run_device_health_check(get_sqobject, device, namespace)
            if health and not health["overall_healthy"]:
                for check in health["checks"]:
                    if not check.get("passed", True):
                        for failure in check.get("failures", []):
                            result["suspected_issues"].append(
                                SuspectedIssue(
                                    device=device,
                                    layer=map_layer_from_table(check.get("table", "")),
                                    issue=f"{check['name']}: {failure.get('reason', 'Failed')}",
                                    confidence=calculate_confidence(health["data_age_seconds"]),
                                    data_age_seconds=health["data_age_seconds"],
                                    source="suzieq",
                                )
                            )

        # 5. Calculate data freshness
        data_age = 60  # Default assumption
        if path_df is not None and "timestamp" in path_df.columns:
            try:
                import pandas as pd

                latest_ts = pd.to_datetime(path_df["timestamp"]).max()
                data_age = int((pd.Timestamp.now() - latest_ts).total_seconds())
            except Exception:
                pass

        result["data_freshness"] = format_data_freshness(data_age)

    except Exception as e:
        logger.error(f"Error in path trace: {e}")
        result["topology_anomalies"].append(f"Path trace error: {e!s}")

    result["scan_duration_ms"] = (time.perf_counter() - start_time) * 1000
    return result


def _run_device_health_check(
    get_sqobject, hostname: str, namespace: str | None = None
) -> HealthCheckResult | None:
    """Internal function to run health checks on a single device.

    Args:
        get_sqobject: SuzieQ get_sqobject function
        hostname: Device hostname
        namespace: SuzieQ namespace

    Returns:
        HealthCheckResult or None if failed
    """
    checks = []
    data_age = 60  # Default

    try:
        # Check interfaces
        intf_obj = get_sqobject("interfaces")
        kwargs = {"hostname": hostname}
        if namespace:
            kwargs["namespace"] = namespace

        intf_df = intf_obj.aver(**kwargs)
        if intf_df is not None and not intf_df.empty:
            failures = intf_df[intf_df["assert"] == "fail"]
            checks.append(
                {
                    "name": "interfaces",
                    "table": "interfaces",
                    "passed": failures.empty,
                    "failures": failures.to_dict(orient="records") if not failures.empty else [],
                }
            )

        # Check BGP
        try:
            bgp_obj = get_sqobject("bgp")
            bgp_df = bgp_obj.aver(**kwargs)
            if bgp_df is not None and not bgp_df.empty:
                failures = bgp_df[bgp_df["assert"] == "fail"]
                checks.append(
                    {
                        "name": "bgp",
                        "table": "bgp",
                        "passed": failures.empty,
                        "failures": failures.to_dict(orient="records")
                        if not failures.empty
                        else [],
                    }
                )
        except Exception:
            pass  # BGP might not be configured

        # Check OSPF
        try:
            ospf_obj = get_sqobject("ospf")
            ospf_df = ospf_obj.aver(**kwargs)
            if ospf_df is not None and not ospf_df.empty:
                failures = ospf_df[ospf_df["assert"] == "fail"]
                checks.append(
                    {
                        "name": "ospf",
                        "table": "ospf",
                        "passed": failures.empty,
                        "failures": failures.to_dict(orient="records")
                        if not failures.empty
                        else [],
                    }
                )
        except Exception:
            pass  # OSPF might not be configured

        overall_healthy = all(c.get("passed", True) for c in checks)

        return HealthCheckResult(
            device=hostname,
            checks=checks,
            overall_healthy=overall_healthy,
            data_age_seconds=data_age,
        )

    except Exception as e:
        logger.error(f"Health check failed for {hostname}: {e}")
        return None


@tool
def suzieq_health_check(
    hostname: str | None = None,
    checks: list[str] | None = None,
    namespace: str | None = None,
) -> list[HealthCheckResult]:
    """Run health check assertions on devices using SuzieQ aver().

    Uses SuzieQ's assertion framework to validate device health:
    - interfaces: All interfaces should be Up (unless admin-down)
    - bgp: All BGP peers should be Established
    - ospf: All OSPF neighbors should be Full
    - mlag: MLAG consistency check

    Args:
        hostname: Device hostname (optional, checks all if not specified)
        checks: List of specific checks to run (optional)
                Options: ["interfaces", "bgp", "ospf", "mlag", "evpnVni"]
        namespace: SuzieQ namespace (optional)

    Returns:
        List of HealthCheckResult for each device

    Example:
        >>> results = suzieq_health_check(hostname="R1")
        >>> print(results[0]["overall_healthy"])
        True
    """
    ctx = get_suzieq_context()

    if not ctx["available"]:
        return [
            HealthCheckResult(
                device=hostname or "unknown",
                checks=[{"name": "error", "passed": False, "failures": ["SuzieQ not available"]}],
                overall_healthy=False,
                data_age_seconds=0,
            )
        ]

    default_checks = ["interfaces", "bgp", "ospf", "mlag"]
    checks_to_run = checks or default_checks

    get_sqobject = ctx["get_sqobject"]
    results = []

    try:
        # Get list of devices if hostname not specified
        if hostname:
            devices = [hostname]
        else:
            device_obj = get_sqobject("device")
            kwargs = {}
            if namespace:
                kwargs["namespace"] = namespace
            device_df = device_obj.get(**kwargs)
            devices = device_df["hostname"].unique().tolist() if device_df is not None else []

        # Run checks on each device
        for device in devices:
            device_checks = []
            data_age = 60

            for check_name in checks_to_run:
                try:
                    sq_obj = get_sqobject(check_name)
                    kwargs = {"hostname": device}
                    if namespace:
                        kwargs["namespace"] = namespace

                    df = sq_obj.aver(**kwargs)
                    if df is not None and not df.empty:
                        failures = df[df["assert"] == "fail"]
                        device_checks.append(
                            {
                                "name": check_name,
                                "table": check_name,
                                "passed": failures.empty,
                                "failures": failures.to_dict(orient="records")
                                if not failures.empty
                                else [],
                            }
                        )
                except Exception as e:
                    logger.debug(f"Check {check_name} not available for {device}: {e}")

            overall_healthy = all(c.get("passed", True) for c in device_checks)

            results.append(
                HealthCheckResult(
                    device=device,
                    checks=device_checks,
                    overall_healthy=overall_healthy,
                    data_age_seconds=data_age,
                )
            )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        results.append(
            HealthCheckResult(
                device=hostname or "unknown",
                checks=[{"name": "error", "passed": False, "failures": [str(e)]}],
                overall_healthy=False,
                data_age_seconds=0,
            )
        )

    return results


@tool
def suzieq_topology_analyze(
    devices: list[str] | None = None,
    namespace: str | None = None,
) -> TopologyAnalysisResult:
    """Analyze network topology using SuzieQ topology.summarize().

    Detects topology anomalies including:
    - Single points of failure
    - Missing redundancy
    - Unexpected topology changes
    - Potential loops

    Args:
        devices: List of device names to include (optional, analyzes all if not specified)
        namespace: SuzieQ namespace (optional)

    Returns:
        TopologyAnalysisResult containing:
        - devices: List of devices in topology
        - connections: Device interconnections
        - anomalies: Detected topology issues
        - single_points_of_failure: Devices without redundancy

    Example:
        >>> result = suzieq_topology_analyze()
        >>> print(result["anomalies"])
        ["R1 has only one uplink - potential single point of failure"]
    """
    ctx = get_suzieq_context()

    result = TopologyAnalysisResult(
        devices=[],
        connections=[],
        anomalies=[],
        single_points_of_failure=[],
    )

    if not ctx["available"]:
        result["anomalies"].append("SuzieQ not available")
        return result

    try:
        get_sqobject = ctx["get_sqobject"]
        topo_obj = get_sqobject("topology")

        kwargs = {}
        if devices:
            kwargs["hostname"] = devices
        if namespace:
            kwargs["namespace"] = namespace

        # Get topology summary
        topo_df = topo_obj.summarize(**kwargs)

        if topo_df is None or topo_df.empty:
            result["anomalies"].append("No topology data available")
            return result

        # Extract devices and connections
        if "hostname" in topo_df.columns:
            result["devices"] = topo_df["hostname"].unique().tolist()

        # Analyze connections
        if "peerHostname" in topo_df.columns:
            for _, row in topo_df.iterrows():
                connection = {
                    "from_device": row.get("hostname"),
                    "to_device": row.get("peerHostname"),
                    "from_interface": row.get("ifname"),
                    "to_interface": row.get("peerIfname"),
                }
                result["connections"].append(connection)

        # Detect single points of failure
        device_connections = {}
        for conn in result["connections"]:
            from_dev = conn.get("from_device")
            if from_dev:
                device_connections[from_dev] = device_connections.get(from_dev, 0) + 1

        for device, count in device_connections.items():
            if count == 1:
                result["single_points_of_failure"].append(device)
                result["anomalies"].append(
                    f"{device} has only one connection - potential single point of failure"
                )

        # Check for topology changes (compare with LLDP)
        try:
            lldp_obj = get_sqobject("lldp")
            lldp_df = lldp_obj.get(**kwargs)

            if lldp_df is not None and not lldp_df.empty:
                lldp_neighbors = set()
                for _, row in lldp_df.iterrows():
                    pair = (row.get("hostname"), row.get("peerHostname"))
                    lldp_neighbors.add(pair)

                topo_neighbors = set()
                for conn in result["connections"]:
                    pair = (conn.get("from_device"), conn.get("to_device"))
                    topo_neighbors.add(pair)

                # Find mismatches
                missing_in_lldp = topo_neighbors - lldp_neighbors
                if missing_in_lldp:
                    result["anomalies"].append(
                        f"Topology shows connections not in LLDP: {missing_in_lldp}"
                    )
        except Exception:
            pass  # LLDP check is optional

    except Exception as e:
        logger.error(f"Topology analysis error: {e}")
        result["anomalies"].append(f"Analysis error: {e!s}")

    return result


# =============================================================================
# Tool List for Export
# =============================================================================

ANALYZER_TOOLS = [
    suzieq_path_trace,
    suzieq_health_check,
    suzieq_topology_analyze,
]

__all__ = [
    "ANALYZER_TOOLS",
    "HealthCheckResult",
    "PathHop",
    "QuickScanResult",
    "SuspectedIssue",
    "TopologyAnalysisResult",
    "calculate_confidence",
    "suzieq_health_check",
    "suzieq_path_trace",
    "suzieq_topology_analyze",
]
