"""
Diff Engine - Compare network state with NetBox SSOT.

Collects data from multiple sources (SuzieQ, OpenConfig, CLI) and
compares against NetBox to identify discrepancies.

LLM-Driven Architecture:
    - Uses LLMDiffEngine for semantic comparison of JSON data
    - LLM understands field mappings automatically (no manual mapping maintenance)
    - Pydantic models validate structured output
    - Supports any NetBox plugin without additional configuration
"""

import asyncio
import logging
from typing import Any, ClassVar

from olav.sync.llm_diff import LLMDiffEngine
from olav.sync.models import (
    DiffResult,
    DiffSeverity,
    DiffSource,
    EntityType,
    ReconciliationReport,
)
from olav.tools.netbox_tool import NetBoxAPITool
from olav.tools.suzieq_parquet_tool import suzieq_query

logger = logging.getLogger(__name__)


class DiffEngine:
    """
    Engine for comparing network state against NetBox SSOT.

    Supports comparison of:
    - Interfaces (status, description, MTU)
    - IP Addresses (assigned, status)
    - VLANs (ID, name)
    - BGP Peers (state, ASN)
    - Device info (model, version, serial)

    Data Sources:
    - SuzieQ Parquet (primary for state data)
    - CLI/NETCONF (fallback for real-time data)
    - OpenConfig YANG (structured config data)
    """

    # Fields that can be auto-corrected without HITL
    AUTO_CORRECT_FIELDS: ClassVar[dict[str, list[str]]] = {
        "interface": ["description", "mtu"],
        "device": ["serial_number", "software_version", "platform"],
        "ip_address": ["status", "dns_name"],
    }

    # Fields that require HITL approval
    HITL_REQUIRED_FIELDS: ClassVar[dict[str, list[str]]] = {
        "interface": ["enabled", "mode", "tagged_vlans", "untagged_vlan"],
        "ip_address": ["address", "assigned_object"],
        "vlan": ["vid", "name", "site"],
        "bgp_peer": ["remote_as", "peer_address"],
    }

    def __init__(
        self,
        netbox_tool: NetBoxAPITool | None = None,
        llm_diff_engine: LLMDiffEngine | None = None,
    ) -> None:
        """
        Initialize DiffEngine.

        Args:
            netbox_tool: NetBox API tool instance (default: create new)
            llm_diff_engine: LLM-driven diff engine (default: create new)
        """
        self.netbox = netbox_tool or NetBoxAPITool()
        self._llm_engine = llm_diff_engine or LLMDiffEngine()

    async def compare_all(
        self,
        devices: list[str],
        entity_types: list[EntityType] | None = None,
    ) -> ReconciliationReport:
        """
        Compare all entity types for given devices.

        Args:
            devices: List of device hostnames to compare
            entity_types: Entity types to compare (default: all)

        Returns:
            ReconciliationReport with all differences found
        """
        if entity_types is None:
            entity_types = [
                EntityType.INTERFACE,
                EntityType.IP_ADDRESS,
                EntityType.DEVICE,
            ]

        report = ReconciliationReport(device_scope=devices)

        # Run comparisons in parallel
        tasks = []
        for entity_type in entity_types:
            if entity_type == EntityType.INTERFACE:
                tasks.append(self._compare_interfaces(devices, report))
            elif entity_type == EntityType.IP_ADDRESS:
                tasks.append(self._compare_ip_addresses(devices, report))
            elif entity_type == EntityType.DEVICE:
                tasks.append(self._compare_devices(devices, report))
            elif entity_type == EntityType.VLAN:
                tasks.append(self._compare_vlans(devices, report))

        await asyncio.gather(*tasks, return_exceptions=True)

        return report

    async def _compare_interfaces(
        self,
        devices: list[str],
        report: ReconciliationReport,
    ) -> None:
        """Compare interface data between SuzieQ and NetBox using LLM."""
        logger.info(f"Comparing interfaces for devices: {devices}")

        for device in devices:
            try:
                # Get SuzieQ interface data
                suzieq_result = await suzieq_query.ainvoke(
                    {
                        "table": "interfaces",
                        "method": "get",
                        "hostname": device,
                    }
                )

                # Get NetBox interface data
                netbox_result = await self.netbox.execute(
                    path="/api/dcim/interfaces/",
                    method="GET",
                    params={"device": device},
                )

                if netbox_result.error:
                    logger.warning(
                        f"NetBox interface query failed for {device}: {netbox_result.error}"
                    )
                    continue

                # Parse results to structured dicts
                suzieq_interfaces = self._parse_suzieq_interfaces(suzieq_result, device)
                netbox_interfaces = self._parse_netbox_interfaces(netbox_result.data)

                # Use LLM-driven comparison
                await self._diff_with_llm(
                    device=device,
                    entity_type=EntityType.INTERFACE,
                    netbox_data=netbox_interfaces,
                    network_data=suzieq_interfaces,
                    report=report,
                    endpoint="/api/dcim/interfaces/",
                )

            except Exception as e:
                logger.error(f"Interface comparison failed for {device}: {e}")

    async def _compare_ip_addresses(
        self,
        devices: list[str],
        report: ReconciliationReport,
    ) -> None:
        """Compare IP address data between SuzieQ and NetBox."""
        logger.info(f"Comparing IP addresses for devices: {devices}")

        for device in devices:
            try:
                # Get SuzieQ interface data (contains ipAddressList field)
                # Note: SuzieQ doesn't have a separate "address" table, IPs are in interfaces
                suzieq_result = await suzieq_query.ainvoke(
                    {
                        "table": "interfaces",
                        "method": "get",
                        "hostname": device,
                    }
                )

                # Get NetBox IP addresses for device
                # First get device ID
                device_result = await self.netbox.execute(
                    path="/api/dcim/devices/",
                    method="GET",
                    params={"name": device},
                )

                # device_result.data is a list from adapter
                if device_result.error or not device_result.data:
                    logger.warning(f"Device {device} not found in NetBox")
                    continue

                device_id = device_result.data[0]["id"]

                # Get IP addresses assigned to device interfaces
                ip_result = await self.netbox.execute(
                    path="/api/ipam/ip-addresses/",
                    method="GET",
                    params={"device_id": device_id},
                )

                if ip_result.error:
                    logger.warning(f"NetBox IP query failed for {device}: {ip_result.error}")
                    continue

                # Parse and compare
                suzieq_ips = self._parse_suzieq_addresses(suzieq_result, device)
                netbox_ips = self._parse_netbox_ips(ip_result.data)

                self._diff_ip_addresses(device, suzieq_ips, netbox_ips, report)

            except Exception as e:
                logger.error(f"IP comparison failed for {device}: {e}")

    async def _compare_devices(
        self,
        devices: list[str],
        report: ReconciliationReport,
    ) -> None:
        """Compare device info between SuzieQ and NetBox.

        Note: SuzieQ 'device' table may not have data if device polling
        hasn't collected it yet. In that case, we skip comparison.
        """
        logger.info(f"Comparing device info for: {devices}")

        for device in devices:
            try:
                # Get SuzieQ device data
                suzieq_result = await suzieq_query.ainvoke(
                    {
                        "table": "device",
                        "method": "get",
                        "hostname": device,
                    }
                )

                # Check if SuzieQ has device table data
                if isinstance(suzieq_result, dict):
                    if suzieq_result.get("status") in ["NO_DATA_FOUND", "SCHEMA_NOT_FOUND"]:
                        logger.info(f"SuzieQ device data not available for {device}, skipping")
                        continue
                    data = suzieq_result.get("data", [])
                    if not data or (len(data) == 1 and data[0].get("status") == "NO_DATA_FOUND"):
                        logger.info(f"SuzieQ device data not available for {device}, skipping")
                        continue

                # Get NetBox device data
                netbox_result = await self.netbox.execute(
                    path="/api/dcim/devices/",
                    method="GET",
                    params={"name": device},
                )

                if netbox_result.error:
                    logger.warning(
                        f"NetBox device query failed for {device}: {netbox_result.error}"
                    )
                    continue

                # netbox_result.data is a list from adapter
                if not netbox_result.data:
                    # Device missing in NetBox
                    report.missing_in_netbox += 1
                    report.add_diff(
                        DiffResult(
                            entity_type=EntityType.DEVICE,
                            device=device,
                            field="existence",
                            network_value="present",
                            netbox_value="missing",
                            severity=DiffSeverity.WARNING,
                            source=DiffSource.SUZIEQ,
                            auto_correctable=False,
                        )
                    )
                    continue

                # Parse and compare
                suzieq_device = self._parse_suzieq_device(suzieq_result, device)
                netbox_device = netbox_result.data[0]

                self._diff_device(device, suzieq_device, netbox_device, report)

            except Exception as e:
                logger.error(f"Device comparison failed for {device}: {e}")

    async def _compare_vlans(
        self,
        devices: list[str],
        report: ReconciliationReport,
    ) -> None:
        """Compare VLAN data between SuzieQ and NetBox."""
        logger.info(f"Comparing VLANs for devices: {devices}")

        for device in devices:
            try:
                # Get SuzieQ VLAN data
                suzieq_result = await suzieq_query.ainvoke(
                    {
                        "table": "vlan",
                        "method": "get",
                        "hostname": device,
                    }
                )

                # Check if SuzieQ has vlan table data
                if isinstance(suzieq_result, dict):
                    if suzieq_result.get("status") in ["NO_DATA_FOUND", "SCHEMA_NOT_FOUND"]:
                        logger.info(f"SuzieQ vlan data not available for {device}, skipping")
                        continue
                    data = suzieq_result.get("data", [])
                    if not data or (len(data) == 1 and data[0].get("status") == "NO_DATA_FOUND"):
                        logger.info(f"SuzieQ vlan data not available for {device}, skipping")
                        continue

                # Get NetBox VLAN data (site-scoped)
                # Need to get device's site first
                device_result = await self.netbox.execute(
                    path="/api/dcim/devices/",
                    method="GET",
                    params={"name": device},
                )

                # device_result.data is a list from adapter
                if device_result.error or not device_result.data:
                    continue

                site_data = device_result.data[0].get("site", {})
                site_id = site_data.get("id") if isinstance(site_data, dict) else None

                if site_id:
                    vlan_result = await self.netbox.execute(
                        path="/api/ipam/vlans/",
                        method="GET",
                        params={"site_id": site_id},
                    )

                    if not vlan_result.error:
                        suzieq_vlans = self._parse_suzieq_vlans(suzieq_result, device)
                        netbox_vlans = self._parse_netbox_vlans(vlan_result.data)
                        self._diff_vlans(device, suzieq_vlans, netbox_vlans, report)

            except Exception as e:
                logger.error(f"VLAN comparison failed for {device}: {e}")

    # ========== LLM-Driven Diff ==========

    async def _diff_with_llm(
        self,
        device: str,
        entity_type: EntityType,
        netbox_data: dict[str, dict[str, Any]],
        network_data: dict[str, dict[str, Any]],
        report: ReconciliationReport,
        endpoint: str,
    ) -> None:
        """
        Use LLM to semantically compare NetBox and network data.

        The LLM understands field mappings automatically (e.g., enabled ↔ adminState)
        and can handle any data structure without manual mapping maintenance.

        Args:
            device: Device hostname
            entity_type: Type of entity being compared
            netbox_data: Dict of entity_name -> entity_data from NetBox
            network_data: Dict of entity_name -> entity_data from network (SuzieQ)
            report: Report to add diffs to
            endpoint: NetBox API endpoint for this entity type
        """
        try:
            # Compare using LLM
            diffs = await self._llm_engine.compare_entities(
                entity_type=entity_type.value,
                device=device,
                netbox_data=netbox_data,
                network_data=network_data,
            )

            # Convert LLM diffs to DiffResult objects
            for diff in diffs:
                # Determine severity and auto-correctability
                field_name = diff.field.split(".")[-1] if "." in diff.field else diff.field
                auto_correct = field_name in self.AUTO_CORRECT_FIELDS.get(entity_type.value, [])
                hitl_required = field_name in self.HITL_REQUIRED_FIELDS.get(entity_type.value, [])

                severity = (
                    DiffSeverity.WARNING
                    if hitl_required or diff.field == "existence"
                    else DiffSeverity.INFO
                )

                # Get NetBox ID if available
                entity_name = diff.identifier or diff.field.split(".")[0]
                netbox_id = None
                if entity_name in netbox_data:
                    netbox_id = netbox_data[entity_name].get("id")

                # Track in report
                if diff.diff_type == "missing_in_netbox":
                    report.missing_in_netbox += 1
                    report.total_entities += 1
                elif diff.diff_type == "missing_in_network":
                    report.missing_in_network += 1
                    report.total_entities += 1
                else:
                    report.total_entities += 1

                report.add_diff(
                    DiffResult(
                        entity_type=entity_type,
                        device=device,
                        field=diff.field,
                        network_value=diff.network_value,
                        netbox_value=diff.netbox_value,
                        severity=severity,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=auto_correct,
                        netbox_id=netbox_id,
                        netbox_endpoint=endpoint,
                        identifier=diff.identifier,
                        additional_context={"reason": diff.reason} if diff.reason else None,
                    )
                )

        except Exception as e:
            logger.error(f"LLM diff failed for {device} {entity_type.value}: {e}")
            # Fall back to simple existence check
            self._diff_existence_only(
                device, entity_type, netbox_data, network_data, report, endpoint
            )

    def _diff_existence_only(
        self,
        device: str,
        entity_type: EntityType,
        netbox_data: dict[str, dict[str, Any]],
        network_data: dict[str, dict[str, Any]],
        report: ReconciliationReport,
        endpoint: str,
    ) -> None:
        """Fallback: only check for existence differences when LLM fails."""
        all_entities = set(netbox_data.keys()) | set(network_data.keys())

        for entity_name in all_entities:
            nb_data = netbox_data.get(entity_name)
            net_data = network_data.get(entity_name)

            if net_data and not nb_data:
                report.missing_in_netbox += 1
                report.total_entities += 1
                report.add_diff(
                    DiffResult(
                        entity_type=entity_type,
                        device=device,
                        field="existence",
                        network_value="present",
                        netbox_value="missing",
                        severity=DiffSeverity.WARNING,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=False,
                        identifier=entity_name,
                    )
                )
            elif nb_data and not net_data:
                report.missing_in_network += 1
                report.total_entities += 1
                report.add_diff(
                    DiffResult(
                        entity_type=entity_type,
                        device=device,
                        field="existence",
                        network_value="missing",
                        netbox_value=entity_name,
                        severity=DiffSeverity.INFO,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=False,
                        netbox_id=nb_data.get("id"),
                        netbox_endpoint=endpoint,
                        identifier=entity_name,
                    )
                )
            else:
                report.add_match()

    # ========== Parsing Helpers ==========

    def _parse_suzieq_interfaces(
        self,
        result: dict[str, Any] | str,
        device: str,
    ) -> dict[str, dict[str, Any]]:
        """Parse SuzieQ interface query result."""
        interfaces = {}

        if isinstance(result, str):
            # Error message
            logger.warning(f"SuzieQ returned error: {result}")
            return interfaces

        data = result.get("data", []) if isinstance(result, dict) else []

        for row in data:
            if row.get("hostname") == device:
                ifname = row.get("ifname", "")
                interfaces[ifname] = {
                    "state": row.get("state", "unknown"),
                    "adminState": row.get("adminState", "unknown"),
                    "mtu": row.get("mtu"),
                    "speed": row.get("speed"),
                    "type": row.get("type"),
                    "description": row.get("description", ""),
                }

        return interfaces

    def _parse_netbox_interfaces(
        self,
        result: list[dict[str, Any]] | dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Parse NetBox interface API result."""
        interfaces = {}

        # Handle both list (from adapter) and dict (raw API response)
        if isinstance(result, list):
            items = result
        else:
            items = result.get("results", [])

        for iface in items:
            name = iface.get("name", "")
            interfaces[name] = {
                "id": iface.get("id"),
                "enabled": iface.get("enabled", True),
                "mtu": iface.get("mtu"),
                "speed": iface.get("speed"),
                "type": iface.get("type", {}).get("value")
                if isinstance(iface.get("type"), dict)
                else iface.get("type"),
                "description": iface.get("description", ""),
            }

        return interfaces

    def _parse_suzieq_addresses(
        self,
        result: dict[str, Any] | str,
        device: str,
    ) -> dict[str, dict[str, Any]]:
        """Parse SuzieQ interface data to extract IP addresses.

        Note: SuzieQ stores IPs in interfaces table as 'ipAddressList' field.
        Each interface can have multiple IP addresses.
        """
        addresses = {}

        if isinstance(result, str):
            return addresses

        data = result.get("data", []) if isinstance(result, dict) else []

        for row in data:
            if row.get("hostname") == device:
                ifname = row.get("ifname", "")
                ip_list = row.get("ipAddressList", [])

                # Handle both list and single IP cases
                if isinstance(ip_list, str):
                    ip_list = [ip_list]

                for ip in ip_list:
                    if ip:
                        addresses[ip] = {
                            "interface": ifname,
                            "vrf": row.get("vrf", "default"),
                            "state": row.get("state"),
                        }

        return addresses

    def _parse_netbox_ips(
        self,
        result: list[dict[str, Any]] | dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Parse NetBox IP address API result."""
        addresses = {}

        # Handle both list (from adapter) and dict (raw API response)
        if isinstance(result, list):
            items = result
        else:
            items = result.get("results", [])

        for ip in items:
            addr = ip.get("address", "")
            status = ip.get("status", {})
            assigned = ip.get("assigned_object")
            addresses[addr] = {
                "id": ip.get("id"),
                "status": status.get("value") if isinstance(status, dict) else status,
                "interface": assigned.get("name") if isinstance(assigned, dict) else None,
                "dns_name": ip.get("dns_name", ""),
            }

        return addresses

    def _parse_suzieq_device(
        self,
        result: dict[str, Any] | str,
        device: str,
    ) -> dict[str, Any]:
        """Parse SuzieQ device query result."""
        if isinstance(result, str):
            return {}

        data = result.get("data", []) if isinstance(result, dict) else []

        for row in data:
            if row.get("hostname") == device:
                return {
                    "model": row.get("model"),
                    "version": row.get("version"),
                    "vendor": row.get("vendor"),
                    "serial": row.get("serialNumber"),
                    "uptime": row.get("uptime"),
                }

        return {}

    def _parse_suzieq_vlans(
        self,
        result: dict[str, Any] | str,
        device: str,
    ) -> dict[int, dict[str, Any]]:
        """Parse SuzieQ VLAN query result."""
        vlans = {}

        if isinstance(result, str):
            return vlans

        data = result.get("data", []) if isinstance(result, dict) else []

        for row in data:
            if row.get("hostname") == device:
                vid = row.get("vlan")
                if vid:
                    vlans[vid] = {
                        "name": row.get("vlanName", ""),
                        "state": row.get("state"),
                        "interfaces": row.get("interfaces", []),
                    }

        return vlans

    def _parse_netbox_vlans(
        self,
        result: list[dict[str, Any]] | dict[str, Any],
    ) -> dict[int, dict[str, Any]]:
        """Parse NetBox VLAN API result."""
        vlans = {}

        # Handle both list (from adapter) and dict (raw API response)
        if isinstance(result, list):
            items = result
        else:
            items = result.get("results", [])

        for vlan in items:
            vid = vlan.get("vid")
            if vid:
                status = vlan.get("status", {})
                vlans[vid] = {
                    "id": vlan.get("id"),
                    "name": vlan.get("name", ""),
                    "status": status.get("value") if isinstance(status, dict) else status,
                }

        return vlans

    # ========== Diff Helpers ==========

    def _diff_interfaces(
        self,
        device: str,
        suzieq: dict[str, dict],
        netbox: dict[str, dict],
        report: ReconciliationReport,
    ) -> None:
        """Generate diffs for interfaces."""
        all_interfaces = set(suzieq.keys()) | set(netbox.keys())

        for ifname in all_interfaces:
            sq_data = suzieq.get(ifname)
            nb_data = netbox.get(ifname)

            if sq_data and not nb_data:
                # Interface in network but not NetBox
                report.missing_in_netbox += 1
                report.total_entities += 1
                report.add_diff(
                    DiffResult(
                        entity_type=EntityType.INTERFACE,
                        device=device,
                        field="existence",
                        network_value="present",
                        netbox_value="missing",
                        severity=DiffSeverity.WARNING,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=False,
                        identifier=ifname,
                        additional_context={
                            "description": sq_data.get("description", ""),
                            "mtu": sq_data.get("mtu"),
                            "enabled": sq_data.get("adminState", "up") == "up",
                            "type": sq_data.get("type"),
                            "speed": sq_data.get("speed"),
                        },
                    )
                )
            elif nb_data and not sq_data:
                # Interface in NetBox but not network
                report.missing_in_network += 1
                report.total_entities += 1
                report.add_diff(
                    DiffResult(
                        entity_type=EntityType.INTERFACE,
                        device=device,
                        field="existence",
                        network_value="missing",
                        netbox_value=ifname,
                        severity=DiffSeverity.INFO,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=False,
                        netbox_id=nb_data.get("id"),
                        netbox_endpoint="/api/dcim/interfaces/",
                        identifier=ifname,
                    )
                )
            else:
                # Both exist - compare fields
                report.total_entities += 1
                has_diff = False

                # Compare MTU
                if sq_data.get("mtu") and nb_data.get("mtu"):
                    if sq_data["mtu"] != nb_data["mtu"]:
                        has_diff = True
                        report.add_diff(
                            DiffResult(
                                entity_type=EntityType.INTERFACE,
                                device=device,
                                field=f"{ifname}.mtu",
                                network_value=sq_data["mtu"],
                                netbox_value=nb_data["mtu"],
                                severity=DiffSeverity.INFO,
                                source=DiffSource.SUZIEQ,
                                auto_correctable=True,
                                netbox_id=nb_data.get("id"),
                                netbox_endpoint="/api/dcim/interfaces/",
                            )
                        )

                # Compare enabled/adminState
                nb_enabled = nb_data.get("enabled", True)
                sq_admin = sq_data.get("adminState", "up") == "up"
                if nb_enabled != sq_admin:
                    has_diff = True
                    report.add_diff(
                        DiffResult(
                            entity_type=EntityType.INTERFACE,
                            device=device,
                            field=f"{ifname}.enabled",
                            network_value=sq_admin,
                            netbox_value=nb_enabled,
                            severity=DiffSeverity.WARNING,
                            source=DiffSource.SUZIEQ,
                            auto_correctable=False,  # HITL required
                            netbox_id=nb_data.get("id"),
                            netbox_endpoint="/api/dcim/interfaces/",
                        )
                    )

                if not has_diff:
                    report.add_match()

    def _diff_ip_addresses(
        self,
        device: str,
        suzieq: dict[str, dict],
        netbox: dict[str, dict],
        report: ReconciliationReport,
    ) -> None:
        """Generate diffs for IP addresses."""
        # Normalize IP formats for comparison
        sq_normalized = {self._normalize_ip(k): v for k, v in suzieq.items()}
        nb_normalized = {self._normalize_ip(k): v for k, v in netbox.items()}

        all_ips = set(sq_normalized.keys()) | set(nb_normalized.keys())

        for ip in all_ips:
            sq_data = sq_normalized.get(ip)
            nb_data = nb_normalized.get(ip)

            if sq_data and not nb_data:
                report.missing_in_netbox += 1
                report.total_entities += 1
                report.add_diff(
                    DiffResult(
                        entity_type=EntityType.IP_ADDRESS,
                        device=device,
                        field="existence",
                        network_value="present",
                        netbox_value="missing",
                        severity=DiffSeverity.WARNING,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=False,  # Adding IPs requires HITL
                        identifier=ip,
                        additional_context={"interface": sq_data.get("interface")},
                    )
                )
            elif nb_data and not sq_data:
                report.missing_in_network += 1
                report.total_entities += 1
                report.add_diff(
                    DiffResult(
                        entity_type=EntityType.IP_ADDRESS,
                        device=device,
                        field="existence",
                        network_value="missing",
                        netbox_value=ip,
                        severity=DiffSeverity.INFO,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=False,
                        netbox_id=nb_data.get("id"),
                        netbox_endpoint="/api/ipam/ip-addresses/",
                        identifier=ip,
                    )
                )
            else:
                report.add_match()

    def _diff_device(
        self,
        device: str,
        suzieq: dict[str, Any],
        netbox: dict[str, Any],
        report: ReconciliationReport,
    ) -> None:
        """Generate diffs for device attributes."""
        report.total_entities += 1
        has_diff = False
        netbox_id = netbox.get("id")

        # Compare software version
        sq_version = suzieq.get("version")
        nb_version = netbox.get("custom_fields", {}).get("software_version")

        if sq_version and nb_version and sq_version != nb_version:
            has_diff = True
            report.add_diff(
                DiffResult(
                    entity_type=EntityType.DEVICE,
                    device=device,
                    field="software_version",
                    network_value=sq_version,
                    netbox_value=nb_version,
                    severity=DiffSeverity.INFO,
                    source=DiffSource.SUZIEQ,
                    auto_correctable=True,
                    netbox_id=netbox_id,
                    netbox_endpoint="/api/dcim/devices/",
                )
            )

        # Compare serial number
        sq_serial = suzieq.get("serial")
        nb_serial = netbox.get("serial")

        if sq_serial and nb_serial and sq_serial != nb_serial:
            has_diff = True
            report.add_diff(
                DiffResult(
                    entity_type=EntityType.DEVICE,
                    device=device,
                    field="serial",
                    network_value=sq_serial,
                    netbox_value=nb_serial,
                    severity=DiffSeverity.WARNING,
                    source=DiffSource.SUZIEQ,
                    auto_correctable=True,
                    netbox_id=netbox_id,
                    netbox_endpoint="/api/dcim/devices/",
                )
            )

        # Compare model/platform
        sq_model = suzieq.get("model")
        nb_platform = netbox.get("platform", {})
        nb_model = nb_platform.get("name") if nb_platform else None

        if sq_model and nb_model and sq_model.lower() != nb_model.lower():
            has_diff = True
            report.add_diff(
                DiffResult(
                    entity_type=EntityType.DEVICE,
                    device=device,
                    field="platform",
                    network_value=sq_model,
                    netbox_value=nb_model,
                    severity=DiffSeverity.INFO,
                    source=DiffSource.SUZIEQ,
                    auto_correctable=False,  # Platform change is significant
                    netbox_id=netbox_id,
                    netbox_endpoint="/api/dcim/devices/",
                )
            )

        if not has_diff:
            report.add_match()

    def _diff_vlans(
        self,
        device: str,
        suzieq: dict[int, dict],
        netbox: dict[int, dict],
        report: ReconciliationReport,
    ) -> None:
        """Generate diffs for VLANs."""
        all_vlans = set(suzieq.keys()) | set(netbox.keys())

        for vid in all_vlans:
            sq_data = suzieq.get(vid)
            nb_data = netbox.get(vid)

            if sq_data and not nb_data:
                report.missing_in_netbox += 1
                report.total_entities += 1
                report.add_diff(
                    DiffResult(
                        entity_type=EntityType.VLAN,
                        device=device,
                        field="existence",
                        network_value=f"VLAN {vid}",
                        netbox_value="missing",
                        severity=DiffSeverity.WARNING,
                        source=DiffSource.SUZIEQ,
                        auto_correctable=False,
                        additional_context={"name": sq_data.get("name")},
                    )
                )
            elif nb_data and not sq_data:
                report.missing_in_network += 1
                report.total_entities += 1
            else:
                # Compare VLAN names
                report.total_entities += 1
                sq_name = sq_data.get("name", "")
                nb_name = nb_data.get("name", "")

                if sq_name and nb_name and sq_name != nb_name:
                    report.add_diff(
                        DiffResult(
                            entity_type=EntityType.VLAN,
                            device=device,
                            field=f"vlan{vid}.name",
                            network_value=sq_name,
                            netbox_value=nb_name,
                            severity=DiffSeverity.INFO,
                            source=DiffSource.SUZIEQ,
                            auto_correctable=False,
                            netbox_id=nb_data.get("id"),
                            netbox_endpoint="/api/ipam/vlans/",
                        )
                    )
                else:
                    report.add_match()

    def _normalize_ip(self, ip: str) -> str:
        """Normalize IP address format for comparison."""
        # Remove /32 for host addresses, normalize spacing
        ip = ip.strip()
        if ip.endswith("/32"):
            ip = ip[:-3]
        return ip

    def is_auto_correctable(self, diff: DiffResult) -> bool:
        """Check if a diff can be auto-corrected."""
        entity_fields = self.AUTO_CORRECT_FIELDS.get(diff.entity_type.value, [])
        field_name = diff.field.split(".")[-1]  # Get last part of field path
        return field_name in entity_fields

    def requires_hitl(self, diff: DiffResult) -> bool:
        """Check if a diff requires HITL approval."""
        entity_fields = self.HITL_REQUIRED_FIELDS.get(diff.entity_type.value, [])
        field_name = diff.field.split(".")[-1]
        return field_name in entity_fields or diff.field == "existence"
