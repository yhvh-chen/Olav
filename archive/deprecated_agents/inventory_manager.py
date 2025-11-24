import csv
import io
import logging
from typing import List, Dict, Any
from olav.tools.netbox_tool import netbox_api_call, netbox_schema_search
from olav.core.settings import settings

logger = logging.getLogger(__name__)

class InventoryManager:
    def __init__(self):
        pass

    def parse_csv(self, csv_content: str) -> List[Dict[str, str]]:
        """Parse CSV content into a list of dictionaries."""
        reader = csv.DictReader(io.StringIO(csv_content))
        return list(reader)

    def import_from_csv(self, csv_content: str) -> Dict[str, Any]:
        """Import devices from CSV to NetBox.

        Expected CSV headers (minimum):
            name, device_role, device_type, site, status, ip_address, platform

        Optional future fields can be ignored safely.
        """
        devices = self.parse_csv(csv_content)
        results = {"success": 0, "failed": 0, "errors": []}

        for device in devices:
            try:
                # 1. Ensure Site exists
                site_name = device.get("site")
                if site_name:
                    self._ensure_object("dcim", "sites", {"name": site_name, "slug": site_name.lower()})

                # 2. Ensure Device Role exists
                role_name = device.get("device_role")
                if role_name:
                    self._ensure_object("dcim", "device-roles", {"name": role_name, "slug": role_name.lower(), "color": "ffffff"})

                # 3. Ensure Device Type exists
                type_name = device.get("device_type")
                if type_name:
                    # Need manufacturer first
                    mfr_name = "Generic"
                    self._ensure_object("dcim", "manufacturers", {"name": mfr_name, "slug": mfr_name.lower()})
                    self._ensure_object("dcim", "device-types", {"model": type_name, "slug": type_name.lower(), "manufacturer": {"name": mfr_name}})

                # 3.a Ensure Platform exists (used by Nornir for driver selection)
                platform_name = device.get("platform")
                if platform_name:
                    self._ensure_object("dcim", "platforms", {"name": platform_name, "slug": platform_name.lower()})

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
                        raise Exception(f"Failed to create device: {resp.get('message')}")
                
                # 5. Add IP (Simplified)
                ip = device.get("ip_address")
                if ip:
                    # Create interface first
                    dev_id = existing["results"][0]["id"] if existing["count"] > 0 else resp["id"]
                    intf_payload = {
                        "device": dev_id,
                        "name": "Management",
                        "type": "virtual"
                    }
                    intf_resp = netbox_api_call("/dcim/interfaces/", "POST", data=intf_payload)
                    
                    # Create IP
                    ip_payload = {
                        "address": ip,
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": intf_resp.get("id")
                    }
                    netbox_api_call("/ipam/ip-addresses/", "POST", data=ip_payload)

                results["success"] += 1

            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Device {device.get('name')}: {str(e)}")

        return results

    def _ensure_object(self, app: str, model: str, data: Dict) -> None:
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
