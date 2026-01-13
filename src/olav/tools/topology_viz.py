"""Topology visualization using pyvis.

This module provides functions for generating interactive HTML visualizations
of network topology using pyvis.
"""

from pathlib import Path

from langchain_core.tools import tool

from olav.tools.topology_graph import TopologyGraph


@tool
def render_topology_html(
    devices: str | None = None,
    viz_type: str = "topology",
    description: str = "full",
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

    Returns:
        Path to the generated HTML file

    Examples:
        >>> render_topology_html(description="bgp")
        "data/visualizations/topology/bgp.html"

        >>> render_topology_html(description="ospf")
        "data/visualizations/topology/ospf.html"

        >>> render_topology_html(description="cdp-lldp")
        "data/visualizations/topology/cdp-lldp.html"
    """
    from pyvis.network import Network

    # Create output directory (data/visualizations, not .olav/data/visualizations)
    output_dir = Path("data/visualizations") / viz_type
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

    # Create pyvis network
    net = Network(
        height="800px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",  # type: ignore
        directed=True,
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

    # Add edges with protocol and interface labels
    for u, v, data in graph.edges(data=True):
        # Build edge label: show local interface and protocol
        label_parts = []
        if data.get("local_port"):
            label_parts.append(data["local_port"])
        if data.get("protocol"):
            label_parts.append(f"({data['protocol']})")

        label = " ".join(label_parts) if label_parts else data.get("protocol", "")

        # Build title with connection info
        title = f"Link: {u} -> {v}\n"
        title += f"Protocol: {data.get('protocol', 'N/A')}\n"
        if data.get("local_port"):
            title += f"Local Interface: {data['local_port']}\n"
        if data.get("remote_port"):
            title += f"Remote Interface: {data['remote_port']}\n"
        title += f"Layer: {data.get('layer', 'N/A')}"

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

    return render_topology_html.invoke(
        {
            "devices": devices_str,
            "viz_type": "topology",
            "description": output_description,
        }
    )


@tool
def visualize_full_topology() -> dict:
    """Generate essential topology visualizations.

    This function generates visualization files for critical protocols only:
    - Full topology (all devices and links)
    - CDP-LLDP Discovery (L1 adjacency, consolidated)
    - OSPF Routing (L3 routing)
    - BGP Routing (L3 routing)

    Returns:
        Dictionary with paths to generated visualization files

    Examples:
        >>> visualize_full_topology()
        {
            "full": "data/visualizations/topology/full.html",
            "cdp-lldp": "data/visualizations/topology/cdp-lldp.html",
            "ospf": "data/visualizations/topology/ospf.html",
            "bgp": "data/visualizations/topology/bgp.html"
        }
    """
    results = {}

    # Generate full topology
    full_path = render_topology_html.invoke({"viz_type": "topology", "description": "full"})
    results["full"] = full_path

    # Generate consolidated CDP-LLDP (L1 adjacency) - single file for both
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
            }
        )
        results["cdp-lldp"] = cdp_lldp_path

    # Generate protocol-specific views (OSPF and BGP only)
    for protocol in ["OSPF", "BGP"]:
        protocol_result = visualize_by_protocol.invoke({"protocol": protocol})
        if not protocol_result.startswith("No ") and not protocol_result.startswith("Invalid"):
            results[protocol.lower()] = protocol_result

    return results
