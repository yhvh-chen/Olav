"""OLAV API Server Authentication.

Single-token authentication mode:
- Token auto-generated on server startup (printed to console)
- Token passed via URL query param or Authorization header
- All authenticated users treated as admin role

This is a simplified auth model optimized for:
- Quick development iteration
- Single-user/team deployments
- Docker/container environments
"""

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from olav.core.settings import settings

# ============================================
# Single Access Token
# ============================================
# Token can be set via environment (multi-worker) or auto-generated (single-worker)
_access_token: str | None = os.environ.get("OLAV_API_TOKEN")
_token_created_at: datetime | None = datetime.now(UTC) if _access_token else None
_token_from_env: bool = _access_token is not None


def generate_access_token() -> str:
    """Generate or return the access token for this server session.

    If OLAV_API_TOKEN is set in environment, returns that (for multi-worker mode).
    Otherwise generates a new token (for single-worker mode).
    """
    global _access_token, _token_created_at, _token_from_env

    # If token already set from environment, return it
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

    # Check token expiration
    if _token_created_at:
        max_age = timedelta(hours=getattr(settings, 'token_max_age_hours', 24))
        if datetime.now(UTC) - _token_created_at > max_age:
            return (False, None)

    # All authenticated users are admin in single-token mode
    return (True, {"username": "admin", "role": "admin", "disabled": False})


# ============================================
# FastAPI Security
# ============================================
def _is_auth_disabled() -> bool:
    """Check if authentication is disabled via environment variable."""
    return os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


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
class User(BaseModel):
    """User model."""
    username: str
    role: str
    disabled: bool = False


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"


# ============================================
# FastAPI Dependencies
# ============================================
async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> User:
    """Validate token and return user.

    If AUTH_DISABLED=true in environment, returns admin user without validation.
    """
    # Check if auth is disabled
    if _is_auth_disabled():
        return User(username="admin", role="admin", disabled=False)

    # Require credentials if auth is enabled
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

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
