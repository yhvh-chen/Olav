from pydantic import BaseModel

class InventoryDevice(BaseModel):
    """Device in the inventory."""
    id: str
    hostname: str
    namespace: str = "default"
    device_type: str | None = None
    vendor: str | None = None
    model: str | None = None
    version: str | None = None
    serial_number: str | None = None
    os: str | None = None
    status: str = "unknown"  # "up", "down", "unknown"
    management_ip: str | None = None
    uptime: str | None = None
    last_polled: str | None = None

class InventoryData(BaseModel):
    """Device inventory data."""
    devices: list[InventoryDevice]
    total: int
    last_updated: str | None = None
