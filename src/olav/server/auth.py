"""Simplified Token Authentication for OLAV API Server.

Single-token mode:
- Token can be set via OLAV_API_TOKEN environment variable (for multi-worker mode)
- Or auto-generated on server startup (for single-worker mode)
- Printed as clickable URL for easy access
- No username/password required
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
# Single Access Token (Environment or Generated)
# ============================================
# For multi-worker deployments, set OLAV_API_TOKEN environment variable
# Otherwise, token is generated fresh on each worker start
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
    
    # Generate new token
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


def validate_token(token: str) -> bool:
    """Validate if the provided token matches the server token."""
    if _access_token is None:
        return False
    
    # Check token expiration (configurable, default 24 hours)
    if _token_created_at:
        max_age = timedelta(hours=getattr(settings, 'token_max_age_hours', 24))
        if datetime.now(UTC) - _token_created_at > max_age:
            return False
    
    return secrets.compare_digest(token, _access_token)


# ============================================
# FastAPI Security
# ============================================
class CustomHTTPBearer(HTTPBearer):
    """HTTPBearer that returns 401 (not 403) for missing credentials."""

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:
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


security = CustomHTTPBearer()


# ============================================
# Data Models
# ============================================
class User(BaseModel):
    """Simplified user model (single admin user)."""
    username: str = "admin"
    role: str = "admin"
    disabled: bool = False


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"


# ============================================
# FastAPI Dependencies
# ============================================
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    """Validate token and return admin user."""
    token = credentials.credentials
    
    if not validate_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return User()


# Convenience type alias
CurrentUser = Annotated[User, Depends(get_current_user)]
