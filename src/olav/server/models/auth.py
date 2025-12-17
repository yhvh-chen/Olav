from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Literal
from enum import Enum

class UserRole(str, Enum):
    """User roles for RBAC."""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

class User(BaseModel):
    """User model."""
    username: str
    role: str
    disabled: bool = False
    client_id: str | None = None  # Session client ID if using session auth

class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"

class SessionToken(BaseModel):
    """Session token for multi-client tracking.

    Each client registers with a unique client_name and receives
    a session token for subsequent API calls.
    """
    token: str = Field(description="Unique session token")
    client_id: str = Field(description="Auto-generated unique client identifier")
    client_name: str = Field(description="Human-readable client name (e.g., 'alice-laptop')")
    role: UserRole = Field(default=UserRole.OPERATOR, description="User role (admin, operator, viewer)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(description="Token expiration time")

    @property
    def is_expired(self) -> bool:
        """Check if this session token has expired."""
        return datetime.now(timezone.utc) > self.expires_at

class RegisterRequest(BaseModel):
    """Request model for client registration."""
    client_name: str = Field(
        min_length=1,
        max_length=64,
        description="Human-readable client name (e.g., 'alice-laptop', 'ci-runner-1')"
    )
    master_token: str = Field(description="Master token for authentication")
    role: UserRole = Field(
        default=UserRole.OPERATOR,
        description="User role: admin (full access), operator (read-write with HITL), viewer (read-only)"
    )

class RegisterResponse(BaseModel):
    """Response model for client registration."""
    session_token: str = Field(description="Session token to use for API calls")
    client_id: str = Field(description="Unique client identifier")
    client_name: str = Field(description="Client name as registered")
    role: UserRole = Field(description="Assigned user role")
    expires_at: datetime = Field(description="Token expiration time")
