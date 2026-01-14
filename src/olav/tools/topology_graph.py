"""Topology graph management using NetworkX.

This module provides the TopologyGraph class for managing network topology
as a NetworkX graph, enabling path analysis and neighbor queries.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import networkx as nx


class TopologyGraph:
    """Network topology graph manager using NetworkX.

    This class loads topology data from DuckDB and provides NetworkX-based
    graph operations for path analysis and neighbor queries.

    Uses MultiDiGraph to support multiple edges between the same node pair
    (e.g., CDP link and OSPF link between R1-R2).

    Attributes:
        db_path: Path to topology database file
        _graph: Cached NetworkX MultiDiGraph instance
        _loaded_at: Timestamp when graph was last loaded
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize topology graph manager.

        Args:
            db_path: Path to topology database (default: .olav/db/network_warehouse.duckdb)
        """
        if db_path is None:
            from config.settings import settings

            db_path = Path(settings.agent_dir) / "db" / "network_warehouse.duckdb"

        self.db_path = Path(db_path)
        self._graph: nx.MultiDiGraph | None = None
        self._loaded_at: datetime | None = None

    def get_graph(self, refresh: bool = False) -> nx.MultiDiGraph:
        """Get the topology graph, loading if necessary.

        Args:
            refresh: Force reload from database

        Returns:
            NetworkX MultiDiGraph with topology data
        """
        if self._graph is None or refresh:
            self._graph = self._load_from_db()
            self._loaded_at = datetime.now()
        return self._graph

    def _load_from_db(self) -> nx.MultiDiGraph:
        """Load topology from DuckDB into NetworkX graph.

        Returns:
            NetworkX MultiDiGraph with devices as nodes and links as edges
        """
        graph = nx.MultiDiGraph()

        # Ensure database exists
        if not self.db_path.exists():
            from olav.core.database import init_topology_db

            init_topology_db(str(self.db_path))

        conn = duckdb.connect(str(self.db_path), read_only=True)

        try:
            # Load device nodes
            devices = conn.execute(
                """
                SELECT name, hostname, platform, mgmt_ip, site, role
                FROM topology_devices
            """
            ).fetchall()

            for name, hostname, platform, mgmt_ip, site, role in devices:
                graph.add_node(
                    name,
                    hostname=hostname,
                    platform=platform,
                    mgmt_ip=mgmt_ip,
                    site=site,
                    role=role,
                )

            # Load link edges
            links = conn.execute(
                """
                SELECT local_device, remote_device, local_port,
                       remote_port, layer, protocol, metadata
                FROM topology_links
            """
            ).fetchall()

            for local, remote, l_port, r_port, layer, protocol, metadata in links:
                graph.add_edge(
                    local,
                    remote,
                    local_port=l_port,
                    remote_port=r_port,
                    layer=layer,
                    protocol=protocol,
                    metadata=metadata,
                )

        finally:
            conn.close()

        return graph

    def shortest_path(self, source: str, target: str) -> list[str]:
        """Calculate shortest path between two devices.

        Args:
            source: Source device name
            target: Target device name

        Returns:
            List of device names forming the path, or empty list if no path exists
        """
        graph = self.get_graph()
        try:
            return nx.shortest_path(graph, source, target)
        except nx.NetworkXNoPath:
            return []
        except nx.NodeNotFound:
            return []

    def get_neighbors(self, device: str, layer: str | None = None) -> list[dict[str, Any]]:
        """Get neighbors of a device.

        Args:
            device: Device name
            layer: Optional filter by layer ('L1' or 'L3')

        Returns:
            List of neighbor dictionaries with device and connection info
        """
        graph = self.get_graph()

        if device not in graph:
            return []

        neighbors = []

        for neighbor in graph.neighbors(device):
            edge_data = graph.get_edge_data(device, neighbor) or {}

            # Filter by layer if specified
            if layer is not None and edge_data.get("layer") != layer:
                continue

            neighbors.append(
                {
                    "device": neighbor,
                    "local_port": edge_data.get("local_port"),
                    "remote_port": edge_data.get("remote_port"),
                    "layer": edge_data.get("layer"),
                    "protocol": edge_data.get("protocol"),
                }
            )

        return neighbors

    def get_topology_age(self) -> str:
        """Get the age of topology data.

        Returns:
            Human-readable age string (e.g., "10 minutes ago") or "Never discovered"
        """
        if self._loaded_at is None:
            # Check database for latest discovery timestamp
            if not self.db_path.exists():
                return "Never discovered"

            conn = duckdb.connect(str(self.db_path), read_only=True)
            try:
                result = conn.execute(
                    """
                    SELECT MAX(discovered_at) FROM topology_links
                """
                ).fetchone()

                if result and result[0]:
                    # Parse timestamp and calculate age
                    last_discovery = result[0]
                    if isinstance(last_discovery, str):
                        last_discovery = datetime.fromisoformat(last_discovery)

                    age = datetime.now() - last_discovery
                    return self._format_timedelta(age)

            finally:
                conn.close()

            return "Never discovered"

        # Use cached load time
        age = datetime.now() - self._loaded_at  # type: ignore[operator]
        return self._format_timedelta(age)

    def _format_timedelta(self, td: timedelta) -> str:
        """Format timedelta as human-readable string.

        Args:
            td: timedelta object

        Returns:
            Formatted string (e.g., "2 hours ago", "5 minutes ago")
        """
        total_seconds = int(td.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds} seconds ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        else:
            days = total_seconds // 86400
            return f"{days} day{'s' if days > 1 else ''} ago"

    def get_device_info(self, device: str) -> dict[str, Any] | None:
        """Get information about a device.

        Args:
            device: Device name

        Returns:
            Device information dict or None if not found
        """
        graph = self.get_graph()

        if device not in graph:
            return None

        return graph.nodes[device]

    def get_all_devices(self) -> list[str]:
        """Get list of all devices in topology.

        Returns:
            List of device names
        """
        graph = self.get_graph()
        return list(graph.nodes())

    def get_link_count(self) -> int:
        """Get total number of links in topology.

        Returns:
            Number of links
        """
        graph = self.get_graph()
        return graph.number_of_edges()
