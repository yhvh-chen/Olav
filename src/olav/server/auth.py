"""OLAV API Server Authentication.

Single-token authentication mode with session support:
- Master token auto-generated on server startup (printed to console)
- Clients can create session tokens for individual tracking
- Token passed via URL query param or Authorization header
- Role-based access control: admin, operator, viewer

This is a simplified auth model optimized for:
- Quick development iteration
- Single-user/team deployments
- Docker/container environments
- Multi-client tracking

Roles:
- admin: Full access, can skip HITL approval
- operator: Read-write with HITL confirmation for write operations
- viewer: Read-only, cannot trigger write workflows
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from config.settings import settings
from olav.server.models.auth import (
    RegisterRequest,
    RegisterResponse,
    SessionToken,
    Token,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


# ============================================
# User Roles
# ============================================
# Moved to olav.server.models.auth

# ============================================
# Single Access Token (Master Token)
# ============================================
# Token can be set via environment (recommended for production/multi-worker)
# or auto-generated (convenient for local single-worker dev).
_access_token: str | None = settings.olav_api_token.strip() or None

# IMPORTANT:
# - If token is provided via environment, treat it as a long-lived master token.
# - If token is auto-generated, it is ephemeral and can be subject to expiration.
_token_from_env: bool = _access_token is not None
_token_created_at: datetime | None = None if _token_from_env else (datetime.now(UTC) if _access_token else None)


# ============================================
# Session Token Storage
# ============================================
# In-memory session store: token -> SessionToken
# TODO: For production, consider Redis or PostgreSQL for persistence
_session_store: dict[str, "SessionToken"] = {}


def generate_access_token() -> str:
    """Generate or return the access token for this server session.

    If OLAV_API_TOKEN is set in environment, returns that (for multi-worker mode).
    Otherwise generates a new token (for single-worker mode).
    """
    global _access_token, _token_created_at

    # If token already set from environment, return it (production / multi-worker)
    if _token_from_env and _access_token:
        return _access_token

    # Generate new token if not already generated
    if _access_token is None:
        _access_token = secrets.token_urlsafe(32)
        _token_created_at = datetime.now(UTC)

    return _access_token


def get_access_token() -> str | None:
    """Get the current access token."""
    return _access_token


def get_token_age_minutes() -> int | None:
    """Get token age in minutes."""
    if _token_created_at is None:
        return None
    delta = datetime.now(UTC) - _token_created_at
    return int(delta.total_seconds() / 60)


def validate_token(token: str) -> tuple[bool, dict | None]:
    """Validate the provided token against the server token.

    Returns:
        Tuple of (is_valid, user_data or None)
    """
    if not _access_token:
        return (False, None)

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, _access_token):
        return (False, None)

    # Check token expiration only for auto-generated (ephemeral) tokens.
    # Environment-provided master tokens are long-lived and are expected to be rotated explicitly.
    if (not _token_from_env) and _token_created_at:
        max_age = timedelta(hours=getattr(settings, "token_max_age_hours", 24))
        if datetime.now(UTC) - _token_created_at > max_age:
            return (False, None)

    # Master token holders are always admin
    return (True, {"username": "admin", "role": UserRole.ADMIN.value, "disabled": False})


# ============================================
# Session Token Management
# ============================================
def create_session(
    client_name: str,
    role: UserRole = UserRole.OPERATOR,
    hours_valid: int | None = None,
) -> "SessionToken":
    """Create a new session token for a client.

    Args:
        client_name: Human-readable client identifier
        role: User role (admin, operator, viewer). Default is operator.
        hours_valid: Token validity in hours (default from settings.session_token_max_age_hours)

    Returns:
        New SessionToken instance
    """
    from olav.server.auth import SessionToken  # Local import to avoid circular

    # Use settings value if not explicitly provided
    if hours_valid is None:
        hours_valid = getattr(settings, "session_token_max_age_hours", 168)

    session = SessionToken(
        token=secrets.token_urlsafe(32),
        client_id=str(uuid.uuid4()),
        client_name=client_name,
        role=role,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=hours_valid),
    )

    # Store session
    _session_store[session.token] = session
    logger.info(f"Created session for client '{client_name}' (id: {session.client_id})")

    return session


def is_master_token_from_env() -> bool:
    """Return True if the server master token comes from OLAV_API_TOKEN env var."""
    return _token_from_env


def validate_session(token: str) -> tuple[bool, "SessionToken | None"]:
    """Validate a session token.

    Returns:
        Tuple of (is_valid, SessionToken or None)
    """
    session = _session_store.get(token)

    if session is None:
        return (False, None)

    if session.is_expired:
        # Clean up expired session
        del _session_store[token]
        logger.info(f"Session expired for client '{session.client_name}'")
        return (False, None)

    return (True, session)


def get_active_sessions() -> list["SessionToken"]:
    """Get all active (non-expired) sessions.

    Also cleans up expired sessions.
    """
    now = datetime.now(UTC)
    expired_tokens = [
        token for token, session in _session_store.items()
        if session.expires_at < now
    ]

    # Clean up expired
    for token in expired_tokens:
        del _session_store[token]

    return list(_session_store.values())


def revoke_session(token: str) -> bool:
    """Revoke a session token.

    Returns:
        True if session was found and revoked, False otherwise
    """
    if token in _session_store:
        session = _session_store.pop(token)
        logger.info(f"Revoked session for client '{session.client_name}'")
        return True
    return False


# ============================================
# FastAPI Security
# ============================================
def _is_auth_disabled() -> bool:
    """Check if authentication is disabled via settings."""
    return bool(settings.auth_disabled)


class CustomHTTPBearer(HTTPBearer):
    """HTTPBearer that returns 401 (not 403) for missing credentials.

    If AUTH_DISABLED=true, allows requests without credentials.
    """

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        # If auth is disabled, don't require credentials
        if _is_auth_disabled():
            # Try to get credentials but don't fail if missing
            authorization = request.headers.get("Authorization")
            if authorization and authorization.startswith("Bearer "):
                return HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials=authorization[7:]
                )
            return None

        try:
            return await super().__call__(request)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            raise


security = CustomHTTPBearer(auto_error=not _is_auth_disabled())


# ============================================
# Data Models
# ============================================
# Moved to olav.server.models.auth


# ============================================
# FastAPI Dependencies
# ============================================
async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> User:
    """Validate token and return user.

    Supports both master token and session token authentication:
    - Master token: Returns admin user (full access)
    - Session token: Returns user with role from session (admin/operator/viewer)

    If AUTH_DISABLED=true in environment, returns admin user without validation.
    """
    # Check if auth is disabled
    if _is_auth_disabled():
        return User(username="admin", role=UserRole.ADMIN.value, disabled=False)

    # Require credentials if auth is enabled
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # First, try session token validation
    is_session_valid, session = validate_session(token)
    if is_session_valid and session:
        return User(
            username=session.client_name,
            role=session.role.value,  # Use role from session
            disabled=False,
            client_id=session.client_id,
        )

    # Fall back to master token validation
    is_valid, user_data = validate_token(token)
    if not is_valid or user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return User(**user_data)


# Convenience type alias
CurrentUser = Annotated[User, Depends(get_current_user)]


# ============================================
# Permission Helpers
# ============================================
def can_access_workflow(role: str, workflow_type: str) -> bool:
    """Check if a role can access a specific workflow type.

    Permission Matrix:
    - QUERY_DIAGNOSTIC: All roles (read-only)
    - DEVICE_EXECUTION: admin, operator only (write operation)
    - NETBOX_MANAGEMENT: admin, operator only (write operation)
    - DEEP_DIVE: admin, operator only (may include write operations)
    - INSPECTION: All roles (read-only analysis)

    Args:
        role: User role string (admin, operator, viewer)
        workflow_type: Workflow type name (QUERY_DIAGNOSTIC, DEVICE_EXECUTION, etc.)

    Returns:
        True if user can access the workflow
    """
    # Read-only workflows accessible by all
    read_only_workflows = {"QUERY_DIAGNOSTIC", "INSPECTION"}

    if workflow_type in read_only_workflows:
        return True

    # Write workflows require operator or admin
    if role in (UserRole.ADMIN.value, UserRole.OPERATOR.value):
        return True

    return False


def get_permission_error_message(role: str, workflow_type: str) -> str:
    """Get user-friendly permission denied message.

    Args:
        role: User role
        workflow_type: Blocked workflow type

    Returns:
        Error message explaining the permission issue
    """
    workflow_names = {
        "DEVICE_EXECUTION": "device configuration changes",
        "NETBOX_MANAGEMENT": "NetBox management operations",
        "DEEP_DIVE": "expert mode analysis",
    }
    action = workflow_names.get(workflow_type, workflow_type.lower())
    return (
        f"⚠️ Permission denied: Your role ({role}) cannot perform {action}. "
        "This action requires 'operator' or 'admin' role. "
        "Please contact an administrator for elevated permissions."
    )