import time
import logging
from fastapi import APIRouter

from olav.server.models.autocomplete import AutocompleteDevicesResponse, AutocompleteSuzieQTablesResponse
from olav.tools.netbox_tool import netbox_api_call

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache for device names (TTL: 5 minutes)
_device_cache: dict = {"devices": [], "timestamp": 0, "ttl": 300}

@router.get(
    "/autocomplete/devices",
    response_model=AutocompleteDevicesResponse,
    tags=["autocomplete"],
    summary="Get device names for autocomplete",
    responses={
        200: {
            "description": "List of device names from NetBox",
            "content": {
                "application/json": {
                    "example": {
                        "devices": ["R1", "R2", "Switch-01", "Firewall-HQ"],
                        "total": 4,
                        "cached": True,
                    }
                }
            },
        },
    },
)
async def autocomplete_devices() -> AutocompleteDevicesResponse:
    """
    Get device names for CLI/client autocomplete.

    Fetches device names from NetBox and caches them for 5 minutes.
    No authentication required for performance.

    **Use Cases**:
    - CLI tab completion for device names
    - Client-side search/filter suggestions
    """
    now = time.time()

    # Check cache
    if _device_cache["devices"] and (now - _device_cache["timestamp"]) < _device_cache["ttl"]:
        return AutocompleteDevicesResponse(
            devices=_device_cache["devices"],
            total=len(_device_cache["devices"]),
            cached=True,
        )

    # Fetch from NetBox
    try:
        result = netbox_api_call(
            endpoint="/dcim/devices/",
            method="GET",
            params={"limit": 1000, "status": "active"},
        )

        if isinstance(result, dict) and "results" in result:
            devices = [d["name"] for d in result["results"] if d.get("name")]
            devices.sort()

            # Update cache
            _device_cache["devices"] = devices
            _device_cache["timestamp"] = now

            return AutocompleteDevicesResponse(
                devices=devices,
                total=len(devices),
                cached=False,
            )
    except Exception as e:
        logger.warning(f"Failed to fetch devices from NetBox: {e}")

    # Return cached or empty
    return AutocompleteDevicesResponse(
        devices=_device_cache["devices"],
        total=len(_device_cache["devices"]),
        cached=True,
    )

@router.get(
    "/autocomplete/tables",
    response_model=AutocompleteSuzieQTablesResponse,
    tags=["autocomplete"],
    summary="Get SuzieQ table names for autocomplete",
    responses={
        200: {
            "description": "List of SuzieQ table names",
            "content": {
                "application/json": {
                    "example": {
                        "tables": ["bgp", "interfaces", "routes", "ospf", "device"],
                        "total": 5,
                    }
                }
            },
        },
    },
)
async def autocomplete_suzieq_tables() -> AutocompleteSuzieQTablesResponse:
    """
    Get SuzieQ table names for CLI/client autocomplete.

    Returns a static list of known SuzieQ tables.
    No authentication required.
    """
    # Static list of SuzieQ tables (from suzieq.shared.schema)
    tables = [
        "arpnd", "bgp", "device", "devconfig", "evpnVni",
        "fs", "ifCounters", "interfaces", "inventory", "lldp",
        "mac", "mlag", "network", "ospf", "path", "routes",
        "sqPoller", "time", "topology", "topmem", "topcpu", "vlan",
    ]

    return AutocompleteSuzieQTablesResponse(
        tables=sorted(tables),
        total=len(tables),
    )
