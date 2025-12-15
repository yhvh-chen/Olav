from pydantic import BaseModel, ConfigDict, Field
from olav.server.models.auth import User

class HealthResponse(BaseModel):
    """Health check response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "0.4.0-beta",
                "environment": "production",
                "postgres_connected": True,
                "orchestrator_ready": True,
            }
        }
    )

    status: str = Field(..., description="Service health status")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Deployment environment")
    postgres_connected: bool = Field(..., description="PostgreSQL connection status")
    orchestrator_ready: bool = Field(..., description="Workflow orchestrator initialization status")


class StatusResponse(BaseModel):
    """Status endpoint response with detailed metrics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "health": {
                    "status": "healthy",
                    "version": "0.4.0-beta",
                    "environment": "production",
                    "postgres_connected": True,
                    "orchestrator_ready": True,
                },
                "user": {
                    "username": "admin",
                    "role": "admin",
                    "disabled": False,
                },
            }
        }
    )

    health: HealthResponse
    user: User


class PublicConfigResponse(BaseModel):
    """Public configuration exposed to clients (non-sensitive only)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "0.4.0-beta",
                "environment": "production",
                "features": {
                    "expert_mode": False,
                    "agentic_rag_enabled": True,
                    "deep_dive_memory_enabled": True,
                },
                "ui": {
                    "default_language": "zh-CN",
                    "streaming_enabled": True,
                    "websocket_heartbeat_seconds": 30,
                },
                "limits": {
                    "max_query_length": 2000,
                    "session_timeout_minutes": 60,
                },
                "workflows": ["query_diagnostic", "device_execution", "netbox_management", "deep_dive"],
            }
        }
    )

    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Deployment environment (local/docker)")
    features: dict = Field(..., description="Enabled feature flags")
    ui: dict = Field(..., description="UI-related configuration")
    limits: dict = Field(..., description="Resource limits and constraints")
    workflows: list[str] = Field(..., description="Available workflow types")
