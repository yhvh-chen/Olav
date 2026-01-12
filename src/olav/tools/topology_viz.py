"""Topology visualization using pyvis.

This module provides functions for generating interactive HTML visualizations
of network topology using pyvis.
"""

from datetime import datetime
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
    directory with a timestamp.

    Args:
        devices: Comma-separated device names to include, or None for all devices
        viz_type: Visualization type - "topology", "path", or "analysis"
        description: Description for the filename (e.g., "site-lab", "R1-R5")

    Returns:
        Path to the generated HTML file

    Examples:
        >>> render_topology_html()
        "data/visualizations/topology/2026-01-12_143052_full.html"

        >>> render_topology_html(devices="R1,R2,R3", description="core")
        "data/visualizations/topology/2026-01-12_150030_core.html"

        >>> render_topology_html(
        ...     devices="R1,R2,R3,R5",
        ...     viz_type="path",
        ...     description="R1-R5"
        ... )
        "data/visualizations/path/2026-01-12_143500_R1-R5.html"
    """
    from pyvis.network import Network

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Create output directory (data/visualizations, not .olav/data/visualizations)
    output_dir = Path("data/visualizations") / viz_type
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{timestamp}_{description}.html"

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
        font_color="white",
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

        # Build title with device info
        title = f"{node}\n"
        title += f"Role: {role}\n"
        title += f"Platform: {node_data.get('platform', 'N/A')}\n"
        title += f"Site: {node_data.get('site', 'N/A')}"

        net.add_node(node, label=node, color=color, title=title)

    # Add edges with protocol labels
    for u, v, data in graph.edges(data=True):
        # Build edge label
        label_parts = []
        if data.get("protocol"):
            label_parts.append(data["protocol"])
        if data.get("local_port"):
            label_parts.append(data["local_port"])

        label = " ".join(label_parts) if label_parts else ""

        # Build title with connection info
        title = f"{u} -> {v}\n"
        title += f"Layer: {data.get('layer', 'N/A')}\n"
        title += f"Protocol: {data.get('protocol', 'N/A')}\n"
        if data.get("local_port"):
            title += f"Local Port: {data['local_port']}\n"
        if data.get("remote_port"):
            title += f"Remote Port: {data['remote_port']}"

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
        "data/visualizations/path/2026-01-12_143500_R1-R5.html"
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
        "data/visualizations/topology/2026-01-12_150030_site-lab.html"
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
def visualize_by_layer(layer: str) -> str:
    """Visualize topology filtered by layer (L1 or L3).

    Args:
        layer: Layer to filter - "L1" (CDP/LLDP) or "L3" (OSPF/BGP)

    Returns:
        Path to the generated HTML file

    Examples:
        >>> visualize_by_layer("L1")
        "data/visualizations/topology/2026-01-12_150030_L1-physical.html"

        >>> visualize_by_layer("L3")
        "data/visualizations/topology/2026-01-12_150030_L3-routing.html"
    """
    topo = TopologyGraph()
    graph = topo.get_graph()

    # Filter edges by layer
    layer_upper = layer.upper()
    if layer_upper not in ("L1", "L3"):
        return f"Invalid layer '{layer}'. Must be 'L1' or 'L3'."

    # Get edges matching the layer
    matching_edges = [
        (u, v)
        for u, v, data in graph.edges(data=True)
        if data.get("layer", "").upper() == layer_upper
    ]

    if not matching_edges:
        return f"No {layer_upper} links found in topology."

    # Get all devices connected by these edges
    devices = set()
    for u, v in matching_edges:
        devices.add(u)
        devices.add(v)

    devices_str = ",".join(sorted(devices))
    description = f"{layer_upper}-physical" if layer_upper == "L1" else f"{layer_upper}-routing"

    return render_topology_html.invoke(
        {
            "devices": devices_str,
            "viz_type": "topology",
            "description": description,
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
        "data/visualizations/topology/2026-01-12_150030_CDP.html"

        >>> visualize_by_protocol("OSPF")
        "data/visualizations/topology/2026-01-12_150030_OSPF.html"
    """
    topo = TopologyGraph()
    graph = topo.get_graph()

    protocol_upper = protocol.upper()
    valid_protocols = ("CDP", "LLDP", "OSPF", "BGP")

    if protocol_upper not in valid_protocols:
        return f"Invalid protocol '{protocol}'. Must be one of: {', '.join(valid_protocols)}."

    # Get edges matching the protocol
    matching_edges = [
        (u, v)
        for u, v, data in graph.edges(data=True)
        if data.get("protocol", "").upper() == protocol_upper
    ]

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
            "description": protocol_upper,
        }
    )


@tool
def visualize_full_topology() -> dict:
    """Generate complete topology visualizations for all layers and protocols.

    This function generates multiple visualization files:
    - Full topology (all devices and links)
    - L1 physical topology (CDP/LLDP links only)
    - L3 routing topology (OSPF/BGP links only)
    - Per-protocol views (CDP, LLDP, OSPF, BGP separately)

    Returns:
        Dictionary with paths to all generated visualization files

    Examples:
        >>> visualize_full_topology()
        {
            "full": "data/visualizations/topology/2026-01-12_150030_full.html",
            "L1": "data/visualizations/topology/2026-01-12_150030_L1-physical.html",
            "L3": "data/visualizations/topology/2026-01-12_150030_L3-routing.html",
            "CDP": "data/visualizations/topology/2026-01-12_150030_CDP.html",
            ...
        }
    """
    results = {}

    # Generate full topology
    full_path = render_topology_html.invoke({"viz_type": "topology", "description": "full"})
    results["full"] = full_path

    # Generate layer-specific views
    for layer in ["L1", "L3"]:
        layer_result = visualize_by_layer.invoke({"layer": layer})
        if not layer_result.startswith("No ") and not layer_result.startswith("Invalid"):
            results[layer] = layer_result

    # Generate protocol-specific views
    for protocol in ["CDP", "LLDP", "OSPF", "BGP"]:
        protocol_result = visualize_by_protocol.invoke({"protocol": protocol})
        if not protocol_result.startswith("No ") and not protocol_result.startswith("Invalid"):
            results[protocol] = protocol_result

    return results
