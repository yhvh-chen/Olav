from pathlib import Path

import pandas as pd
from fastapi import APIRouter

import logging

from olav.server.auth import CurrentUser
from olav.server.models import InventoryData, InventoryDevice

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get(
    "/inventory",
    response_model=InventoryData,
    tags=["inventory"],
    summary="Get device inventory",
    responses={
        200: {
            "description": "Device inventory data",
            "content": {
                "application/json": {
                    "example": {
                        "devices": [
                            {
                                "id": "R1",
                                "hostname": "R1",
                                "namespace": "default",
                                "device_type": "router",
                                "vendor": "Cisco",
                                "model": "ISRV",
                                "status": "up",
                                "management_ip": "192.168.100.101"
                            }
                        ],
                        "total": 6,
                        "last_updated": "2025-12-01T10:00:00Z"
                    }
                }
            },
        },
    },
)
async def get_inventory(current_user: CurrentUser) -> InventoryData:
    """
    Get device inventory from SuzieQ device data.

    Returns a list of all network devices with their basic information
    including hostname, vendor, model, status, and management IP.

    **Required**: Bearer token authentication

    **Example Request**:
    ```bash
    curl http://localhost:8000/inventory \\
      -H "Authorization: Bearer <token>"
    ```
    """
    devices: list[InventoryDevice] = []
    seen_devices: set[str] = set()
    last_updated: str | None = None

    parquet_dir = Path("data/suzieq-parquet")

    try:
        import pyarrow.parquet as pq

        # SuzieQ stores coalesced data in 'coalesced' subfolder
        device_path = parquet_dir / "coalesced" / "device"
        if not device_path.exists():
            # Fallback to raw device folder if coalesced doesn't exist
            device_path = parquet_dir / "device"

        if device_path.exists():
            try:
                # Read entire dataset with partitioning
                device_table = pq.read_table(str(device_path))
                df_device = device_table.to_pandas()

                if not df_device.empty:
                    # Get latest record per hostname
                    if "timestamp" in df_device.columns and "hostname" in df_device.columns:
                        df_device = df_device.sort_values("timestamp", ascending=False)
                        df_device = df_device.drop_duplicates(subset=["hostname"], keep="first")
                        last_updated = df_device["timestamp"].max()
                        if pd.notna(last_updated):
                            last_updated = pd.Timestamp(last_updated).isoformat()

                    for _, row in df_device.iterrows():
                        hostname = str(row.get("hostname", "unknown"))
                        logger.info(f"Processing {hostname}. Keys: {row.index.tolist()}")
                        if hostname and hostname not in seen_devices:
                            seen_devices.add(hostname)

                            # Parse uptime if available
                            uptime_str = None
                            uptime_val = row.get("uptime")

                            # Fallback to bootupTimestamp calculation
                            if (pd.isna(uptime_val) or not uptime_val):
                                # Check if bootupTimestamp exists in index
                                if "bootupTimestamp" in row.index:
                                    bootup_ts = row["bootupTimestamp"]
                                    logger.info(f"Device {hostname} bootupTimestamp: {bootup_ts}")
                                    if pd.notna(bootup_ts):
                                        try:
                                            import time
                                            current_ts = time.time()
                                            bootup_ts_float = float(bootup_ts)
                                            if bootup_ts_float < current_ts:
                                                uptime_secs = current_ts - bootup_ts_float
                                                uptime_val = uptime_secs
                                        except Exception:
                                            pass
                                else:
                                    logger.warning(f"Device {hostname} missing bootupTimestamp column")

                            if pd.notna(uptime_val) and uptime_val:
                                try:
                                    # Uptime is typically in seconds
                                    uptime_secs = float(uptime_val)
                                    days = int(uptime_secs // 86400)
                                    hours = int((uptime_secs % 86400) // 3600)
                                    mins = int((uptime_secs % 3600) // 60)
                                    if days > 0:
                                        uptime_str = f"{days}d {hours}h"
                                    elif hours > 0:
                                        uptime_str = f"{hours}h {mins}m"
                                    else:
                                        uptime_str = f"{mins}m"
                                except (ValueError, TypeError):
                                    uptime_str = str(uptime_val)

                            # Get timestamp as last_polled
                            last_polled = None
                            ts = row.get("timestamp")
                            if pd.notna(ts):
                                last_polled = pd.Timestamp(ts).isoformat()

                            devices.append(InventoryDevice(
                                id=hostname,
                                hostname=hostname,
                                namespace=str(row.get("namespace", "default")) or "default",
                                device_type=str(row.get("devtype", "")) or None,
                                vendor=str(row.get("vendor", "")) or None,
                                model=str(row.get("model", "")) or None,
                                version=str(row.get("version", "")) or None,
                                serial_number=str(row.get("serialNumber", "")) or None,
                                os=str(row.get("os", "")) or None,
                                status="up" if row.get("status") == "alive" else "down",
                                management_ip=str(row.get("address", "")) or None,
                                uptime=uptime_str,
                                last_polled=last_polled,
                            ))
            except Exception as e:
                logger.warning(f"Failed to read device parquet: {e}")

    except Exception as e:
        logger.error(f"Failed to load inventory: {e}")
        return InventoryData(devices=[], total=0, last_updated=None)

    return InventoryData(
        devices=devices,
        total=len(devices),
        last_updated=last_updated,
    )
