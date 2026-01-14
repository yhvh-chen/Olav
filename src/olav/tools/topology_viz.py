"""Topology visualization using pyvis.

This module provides functions for generating interactive HTML visualizations
of network topology using pyvis.
"""

import json
import re
from pathlib import Path

from langchain_core.tools import tool

from olav.tools.topology_graph import TopologyGraph

# =============================================================================
# Helper Functions
# =============================================================================


def _shorten_interface(name: str) -> str:
    """Shorten interface name to abbreviated form.

    Examples:
        GigabitEthernet0/2 -> Gi0/2
        Ethernet0/0 -> Eth0/0
        Gig 2 -> Gi2
        FastEthernet0/1 -> Fa0/1
    """
    if not name:
        return ""

    # Common interface abbreviations
    patterns = [
        (r"GigabitEthernet\s*(\S+)", r"Gi\1"),
        (r"Gig\s*(\S+)", r"Gi\1"),
        (r"FastEthernet\s*(\S+)", r"Fa\1"),
        (r"Ethernet\s*(\S+)", r"Eth\1"),
        (r"Eth\s*(\S+)", r"Eth\1"),
        (r"TenGigabitEthernet\s*(\S+)", r"Te\1"),
        (r"FortyGigabitEthernet\s*(\S+)", r"Fo\1"),
        (r"Loopback\s*(\S+)", r"Lo\1"),
        (r"Vlan\s*(\S+)", r"Vl\1"),
    ]

    result = name.strip()
    for pattern, replacement in patterns:
        match = re.match(pattern, result, re.IGNORECASE)
        if match:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            break

    return result


@tool
def render_topology_html(
    devices: str | None = None,
    viz_type: str = "topology",
    description: str = "full",
    protocols: str | None = None,
) -> str:
    """Generate interactive HTML topology visualization.

    This function creates an interactive HTML visualization of the network
    topology using pyvis. The visualization is saved to the data/visualizations
    directory. Files are named by protocol (cdp-lldp, bgp, ospf, etc.) without
    timestamps. Files are updated on each run (no date-based versions).

    Args:
        devices: Comma-separated device names to include, or None for all devices
        viz_type: Visualization type - "topology", "path", or "analysis"
        description: Protocol or description name (e.g., "bgp", "ospf", "cdp-lldp")
        protocols: Comma-separated protocols to filter edges (e.g., "CDP,LLDP" or "OSPF")

    Returns:
        Path to the generated HTML file

    Examples:
        >>> render_topology_html(description="bgp", protocols="BGP")
        "data/visualizations/topology/bgp.html"

        >>> render_topology_html(description="ospf", protocols="OSPF")
        "data/visualizations/topology/ospf.html"

        >>> render_topology_html(description="cdp-lldp", protocols="CDP,LLDP")
        "exports/visualizations/topology/cdp-lldp.html"
    """
    from pyvis.network import Network

    # Create output directory (exports/visualizations, not .olav/db/)
    output_dir = Path("exports/visualizations") / viz_type
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use description as filename without timestamp (forces update each run)
    output_path = output_dir / f"{description}.html"

    # Get topology graph
    topo = TopologyGraph()
    graph = topo.get_graph()

    # Filter devices if specified
    device_list = None
    if devices:
        device_list = [d.strip() for d in devices.split(",")]
        # Verify devices exist in graph
        valid_devices = [d for d in device_list if d in graph.nodes()]
        if valid_devices:
            graph = graph.subgraph(valid_devices).copy()

    # Create pyvis network (undirected for cleaner visualization)
    net = Network(
        height="800px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",  # type: ignore
        directed=False,  # Undirected = single link between nodes
    )

    # Configure physics engine for better layout
    net.barnes_hut(
        gravity=-5000,
        central_gravity=0.3,
        spring_length=150,
        spring_strength=0.05,
    )

    # Color map for device roles
    color_map = {
        "core": "#4CAF50",  # Green
        "distribution": "#2196F3",  # Blue
        "access": "#FF9800",  # Orange
        "border": "#9C27B0",  # Purple
        "unknown": "#607D8B",  # Gray
    }

    # Add nodes with role-based coloring
    for node in graph.nodes():
        node_data = graph.nodes[node]
        role = node_data.get("role", "unknown")
        color = color_map.get(role, color_map["unknown"])

        # Use hostname for display, fall back to device name
        hostname = node_data.get("hostname", node)

        # Build title with device info
        title = f"Device: {node}\n"
        title += f"Hostname: {hostname}\n"
        title += f"Role: {role}\n"
        title += f"Platform: {node_data.get('platform', 'N/A')}\n"
        title += f"IP: {node_data.get('mgmt_ip', 'N/A')}\n"
        title += f"Site: {node_data.get('site', 'N/A')}"

        net.add_node(node, label=hostname, color=color, title=title)

    # Build protocol filter set
    protocol_filter: set[str] | None = None
    if protocols:
        protocol_filter = {p.strip().upper() for p in protocols.split(",")}

    # Add edges with interface labels (deduplicate bidirectional links)
    seen_edges: set[tuple[str, str]] = set()
    for u, v, data in graph.edges(data=True):
        # Filter by protocol if specified
        edge_protocol = data.get("protocol", "").upper()
        if protocol_filter and edge_protocol not in protocol_filter:
            continue  # Skip edge not matching protocol filter

        # Create canonical edge key (sorted to deduplicate A-B and B-A)
        edge_key = tuple(sorted([u, v]))
        if edge_key in seen_edges:
            continue  # Skip duplicate reverse edge
        seen_edges.add(edge_key)

        # Build edge label: show both ports with short names
        local_port = data.get("local_port", "")
        remote_port = data.get("remote_port", "")

        # Shorten interface names for display
        local_short = _shorten_interface(local_port)
        remote_short = _shorten_interface(remote_port)

        # Build protocol-specific label
        protocol = data.get("protocol", "")

        # Parse metadata for IPs and AS info
        metadata_raw = data.get("metadata", "{}")
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except json.JSONDecodeError:
                metadata = {}
        else:
            metadata = metadata_raw or {}
        local_ip = metadata.get("local_ip", "")
        remote_ip = metadata.get("remote_ip", "")
        local_as = metadata.get("local_as", "")
        remote_as = metadata.get("remote_as", "")

        # Determine BGP type (iBGP/eBGP) for label and title
        bgp_type = ""
        if protocol == "BGP" and local_as and remote_as:
            bgp_type = "iBGP" if local_as == remote_as else "eBGP"

        # Build edge label based on protocol
        if protocol == "BGP":
            # BGP: show iBGP or eBGP as label
            label = bgp_type if bgp_type else "BGP"
        elif protocol == "OSPF":
            # OSPF: show G1↔G2 style (both local and remote interface)
            if local_short and remote_short:
                label = f"{local_short}↔{remote_short}"
            elif local_short:
                label = local_short
            else:
                label = protocol
        elif local_short and remote_short:
            # CDP/LLDP: show both interfaces
            label = f"{local_short}↔{remote_short}"
        elif local_short:
            label = local_short
        else:
            label = protocol

        # Build detailed title for hover
        title = f"🔗 Link: {u} ↔ {v}\n"
        title += "━━━━━━━━━━━━━━━━━━━━━\n"

        # Protocol-specific info in title
        if protocol == "BGP" and bgp_type:
            title += f"Protocol: {bgp_type}\n"
            title += f"AS: {local_as} ↔ {remote_as}\n"
        else:
            title += f"Protocol: {protocol}\n"

        title += f"Layer: {data.get('layer', 'N/A')}\n"
        title += "━━━━━━━━━━━━━━━━━━━━━\n"

        # Show connection info for each side
        # Format: Device: Interface (IP) - but only show non-empty parts
        if protocol == "BGP":
            # BGP: show router IDs (IPs) without N/A
            if local_ip:
                title += f"{u}: {local_ip}\n"
            if remote_ip:
                title += f"{v}: {remote_ip}\n"
        elif protocol in ("CDP", "LLDP"):
            # CDP/LLDP: show interfaces, add IPs if available
            if local_port:
                title += f"{u}: {local_port}"
                if local_ip:
                    title += f" ({local_ip})"
                title += "\n"
            if remote_port:
                title += f"{v}: {remote_port}"
                if remote_ip:
                    title += f" ({remote_ip})"
                title += "\n"
        else:
            # OSPF: show both interfaces and IPs (enriched from cross-reference)
            if local_port:
                title += f"{u}: {_shorten_interface(local_port)}"
                if local_ip:
                    title += f" ({local_ip})"
                title += "\n"
            if remote_port:
                title += f"{v}: {_shorten_interface(remote_port)}"
                if remote_ip:
                    title += f" ({remote_ip})"
                title += "\n"
            elif remote_ip:
                title += f"{v}: {remote_ip}\n"

        net.add_edge(u, v, label=label, title=title)

    # Save visualization
    net.save_graph(str(output_path))

    return str(output_path)


@tool
def visualize_path(source: str, destination: str) -> str:
    """Visualize the path between two devices.

    This function computes the shortest path between two devices and
    generates an interactive HTML visualization of that path.

    Args:
        source: Source device name
        destination: Destination device name

    Returns:
        Path to the generated HTML file, or error message

    Examples:
        >>> visualize_path("R1", "R5")
        "data/visualizations/path/R1-R5.html"
    """
    topo = TopologyGraph()
    path = topo.shortest_path(source, destination)

    if not path:
        return f"No path found between {source} and {destination}."

    # Create visualization with path devices
    devices_str = ",".join(path)
    description = (
        f"{source}-{'-'.join(path[1:-1])}-{destination}"
        if len(path) > 2
        else f"{source}-{destination}"
    )

    return render_topology_html.invoke(
        {
            "devices": devices_str,
            "viz_type": "path",
            "description": description,
        }
    )


@tool
def visualize_site(site: str) -> str:
    """Visualize topology for a specific site.

    Args:
        site: Site name to filter devices

    Returns:
        Path to the generated HTML file

    Examples:
        >>> visualize_site("lab")
        "data/visualizations/topology/site-lab.html"
    """
    topo = TopologyGraph()
    graph = topo.get_graph()

    # Filter devices by site
    site_devices = [
        node
        for node, data in graph.nodes(data=True)
        if data.get("site", "").lower() == site.lower()
    ]

    if not site_devices:
        return f"No devices found for site '{site}'."

    devices_str = ",".join(site_devices)
    return render_topology_html.invoke(
        {
            "devices": devices_str,
            "viz_type": "topology",
            "description": f"site-{site}",
        }
    )


@tool
def visualize_by_protocol(protocol: str) -> str:
    """Visualize topology filtered by protocol.

    Args:
        protocol: Protocol to filter - "CDP", "LLDP", "OSPF", or "BGP"

    Returns:
        Path to the generated HTML file

    Examples:
        >>> visualize_by_protocol("CDP")
        "data/visualizations/topology/cdp-lldp.html"

        >>> visualize_by_protocol("OSPF")
        "data/visualizations/topology/ospf.html"
    """
    topo = TopologyGraph()
    graph = topo.get_graph()

    protocol_upper = protocol.upper()
    valid_protocols = ("CDP", "LLDP", "OSPF", "BGP")

    if protocol_upper not in valid_protocols:
        return f"Invalid protocol '{protocol}'. Must be one of: {', '.join(valid_protocols)}."

    # For CDP/LLDP, check both protocols
    if protocol_upper in ("CDP", "LLDP"):
        matching_edges = [
            (u, v)
            for u, v, data in graph.edges(data=True)
            if data.get("protocol", "").upper() in ("CDP", "LLDP")
        ]
        output_description = "cdp-lldp"
    else:
        # For OSPF/BGP, match exact protocol
        matching_edges = [
            (u, v)
            for u, v, data in graph.edges(data=True)
            if data.get("protocol", "").upper() == protocol_upper
        ]
        output_description = protocol_upper.lower()

    if not matching_edges:
        return f"No {protocol_upper} links found in topology."

    # Get all devices connected by these edges
    devices = set()
    for u, v in matching_edges:
        devices.add(u)
        devices.add(v)

    devices_str = ",".join(sorted(devices))

    # Build protocol filter string
    if protocol_upper in ("CDP", "LLDP"):
        protocols_filter = "CDP,LLDP"
    else:
        protocols_filter = protocol_upper

    return render_topology_html.invoke(
        {
            "devices": devices_str,
            "viz_type": "topology",
            "description": output_description,
            "protocols": protocols_filter,
        }
    )


@tool
def visualize_full_topology() -> dict:
    """Generate protocol-specific topology visualizations.

    This function generates visualization files for discovery protocols:
    - CDP-LLDP Discovery (L1/L2 adjacency, consolidated)
    - OSPF Routing (L3 routing)
    - BGP Routing (L3 routing)

    Note: 'full' topology is deprecated - use protocol-specific views.

    Returns:
        Dictionary with paths to generated visualization files

    Examples:
        >>> visualize_full_topology()
        {
            "cdp-lldp": "data/visualizations/topology/cdp-lldp.html",
            "ospf": "data/visualizations/topology/ospf.html",
            "bgp": "data/visualizations/topology/bgp.html"
        }
    """
    results = {}

    # NOTE: 'full' topology deprecated - generate protocol-specific views only

    # Generate consolidated CDP-LLDP (L1/L2 adjacency) - single file for both
    topo = TopologyGraph()
    graph = topo.get_graph()

    # Get edges matching CDP or LLDP
    cdp_lldp_edges = [
        (u, v)
        for u, v, data in graph.edges(data=True)
        if data.get("protocol", "").upper() in ("CDP", "LLDP")
    ]

    if cdp_lldp_edges:
        devices = set()
        for u, v in cdp_lldp_edges:
            devices.add(u)
            devices.add(v)
        devices_str = ",".join(sorted(devices))
        cdp_lldp_path = render_topology_html.invoke(
            {
                "devices": devices_str,
                "viz_type": "topology",
                "description": "cdp-lldp",
                "protocols": "CDP,LLDP",
            }
        )
        results["cdp-lldp"] = cdp_lldp_path

    # Generate protocol-specific views (OSPF and BGP only)
    for protocol in ["OSPF", "BGP"]:
        protocol_result = visualize_by_protocol.invoke({"protocol": protocol})
        if not protocol_result.startswith("No ") and not protocol_result.startswith("Invalid"):
            results[protocol.lower()] = protocol_result

    return results
