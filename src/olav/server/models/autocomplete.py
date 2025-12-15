from pydantic import BaseModel, Field

class AutocompleteDevicesResponse(BaseModel):
    """Response for device autocomplete endpoint."""

    devices: list[str] = Field(..., description="List of device names for autocomplete")
    total: int = Field(..., description="Total number of devices")
    cached: bool = Field(default=False, description="Whether the result was from cache")


class AutocompleteSuzieQTablesResponse(BaseModel):
    """Response for SuzieQ tables autocomplete endpoint."""

    tables: list[str] = Field(..., description="List of SuzieQ table names")
    total: int = Field(..., description="Total number of tables")
