"""Inventory Manager - Bootstrap NetBox from CSV inventory.

Two modes:
1. Bootstrap Mode: Import devices from CSV if NetBox is empty (first-time setup)
2. Skip Mode: Skip import if NetBox already has devices (existing deployment)

Usage:
    manager = InventoryManager()
    result = manager.import_from_csv(csv_content, force=False)  # Auto-detect mode
    result = manager.import_from_csv(csv_content, force=True)   # Force import
"""

import csv
import io
import logging
from typing import Any

from olav.tools.netbox_tool import netbox_api_call

logger = logging.getLogger(__name__)


class InventoryManager:
    def __init__(self) -> None:
        self.dry_run = False

    def is_netbox_empty(self) -> bool:
        """Check if NetBox has any devices (used to determine bootstrap mode)."""
        try:
            resp = netbox_api_call("/dcim/devices/", "GET", params={"limit": 1})
            device_count = resp.get("count", 0)
            logger.info(f"NetBox device count: {device_count}")
            return device_count == 0
        except Exception as e:
            logger.error(f"Failed to check NetBox status: {e}")
            return True  # Assume empty on error (allow bootstrap)

    def parse_csv(self, csv_content: str) -> list[dict[str, str]]:
        """Parse CSV content into a list of dictionaries."""
        reader = csv.DictReader(io.StringIO(csv_content))
        return list(reader)

    def import_from_csv(self, csv_content: str, force: bool = False) -> dict[str, Any]:
        """Import devices from CSV to NetBox.

        Args:
            csv_content: CSV string with device inventory
            force: If False (default), skip import if NetBox has devices.
                   If True, force import regardless of NetBox state.

        Returns:
            Dict with keys: mode, success, failed, errors, skipped

        Expected CSV headers (minimum):
            name, device_role, device_type, site, status, ip_address, platform

        Optional future fields can be ignored safely.
        """
        # Mode detection
        is_empty = self.is_netbox_empty()
        mode = "bootstrap" if is_empty else "skip"

        if not force and not is_empty:
            logger.info("NetBox already has devices. Skipping import (use force=True to override)")
            return {
                "mode": "skip",
                "success": 0,
                "failed": 0,
                "errors": [],
                "skipped": True,
                "message": "NetBox already initialized. Use force=True to import anyway.",
            }

        if force and not is_empty:
            logger.warning("Force mode enabled. Importing devices into non-empty NetBox.")
            mode = "force"

        devices = self.parse_csv(csv_content)
        results = {"mode": mode, "success": 0, "failed": 0, "errors": [], "skipped": False}

        for device in devices:
            try:
                # 1. Ensure Site exists
                site_name = device.get("site")
                if site_name:
                    self._ensure_object(
                        "dcim", "sites", {"name": site_name, "slug": site_name.lower()}
                    )

                # 2. Ensure Device Role exists
                role_name = device.get("device_role")
                if role_name:
                    self._ensure_object(
                        "dcim",
                        "device-roles",
                        {"name": role_name, "slug": role_name.lower(), "color": "ffffff"},
                    )

                # 3. Ensure Device Type exists
                type_name = device.get("device_type")
                if type_name:
                    # Need manufacturer first
                    mfr_name = "Generic"
                    self._ensure_object(
                        "dcim", "manufacturers", {"name": mfr_name, "slug": mfr_name.lower()}
                    )
                    self._ensure_object(
                        "dcim",
                        "device-types",
                        {
                            "model": type_name,
                            "slug": type_name.lower(),
                            "manufacturer": {"name": mfr_name},
                        },
                    )

                # 3.a Ensure Platform exists (used by Nornir for driver selection)
                platform_name = device.get("platform")
                if platform_name:
                    self._ensure_object(
                        "dcim", "platforms", {"name": platform_name, "slug": platform_name.lower()}
                    )

                # 4. Create Device
                payload = {
                    "name": device["name"],
                    "device_type": {"model": device["device_type"]},
                    "role": {"name": device["device_role"]},
                    "site": {"name": device["site"]},
                    "status": device.get("status", "active"),
                }
                if platform_name:
                    payload["platform"] = {"name": platform_name}

                # Check if device exists
                existing = netbox_api_call("/dcim/devices/", "GET", params={"name": device["name"]})
                if existing.get("count", 0) == 0:
                    resp = netbox_api_call("/dcim/devices/", "POST", data=payload)
                    if resp.get("status") == "error":
                        msg = f"Failed to create device: {resp.get('message')}"
                        raise Exception(msg)

                # 5. Add IP (Simplified)
                ip = device.get("ip_address")
                if ip:
                    # Create interface first
                    dev_id = existing["results"][0]["id"] if existing["count"] > 0 else resp["id"]
                    intf_payload = {"device": dev_id, "name": "Management", "type": "virtual"}
                    intf_resp = netbox_api_call("/dcim/interfaces/", "POST", data=intf_payload)

                    # Create IP
                    ip_payload = {
                        "address": ip,
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": intf_resp.get("id"),
                    }
                    netbox_api_call("/ipam/ip-addresses/", "POST", data=ip_payload)

                results["success"] += 1

            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Device {device.get('name')}: {e!s}")

        return results

    def _ensure_object(self, app: str, model: str, data: dict) -> None:
        """Ensure a NetBox object exists, create if not."""
        # Simplified lookup by name or slug
        lookup = {}
        if "name" in data:
            lookup["name"] = data["name"]
        elif "slug" in data:
            lookup["slug"] = data["slug"]

        resp = netbox_api_call(f"/{app}/{model}/", "GET", params=lookup)
        if resp.get("count", 0) == 0:
            netbox_api_call(f"/{app}/{model}/", "POST", data=data)
