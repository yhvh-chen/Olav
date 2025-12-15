"""Authentication API Router.

This module provides endpoints for:
- User information (/me)
- Client registration (/auth/register)
- Session management (/auth/sessions, /auth/revoke)
"""

import logging

from fastapi import APIRouter, HTTPException, status
from olav.server.auth import (
    CurrentUser,
    RegisterRequest,
    RegisterResponse,
    User,
    create_session,
    get_active_sessions,
    revoke_session,
    validate_token,
)

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


@router.get(
    "/me",
    response_model=User,
    summary="Get current user info",
    responses={
        200: {
            "description": "Authenticated user information",
            "content": {
                "application/json": {
                    "example": {
                        "username": "admin",
                        "role": "admin",
                        "disabled": False,
                    }
                }
            },
        },
        401: {
            "description": "Missing or invalid token",
            "content": {
                "application/json": {"example": {"detail": "Invalid or expired token"}}
            },
        },
    },
)
async def get_current_user_info(current_user: CurrentUser) -> User:
    """
    Get current authenticated user information.

    **Required**: Bearer token from server startup

    Useful for:
    - Verifying token validity
    - Client authentication check

    **Example Request**:
    ```bash
    curl http://localhost:8000/me \\
      -H "Authorization: Bearer <token-from-startup>"
    ```
    """
    return current_user


@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    summary="Register a new client and get session token",
    responses={
        200: {
            "description": "Client registered successfully",
            "content": {
                "application/json": {
                    "example": {
                        "session_token": "abc123...",
                        "client_id": "550e8400-e29b-41d4-a716-446655440000",
                        "client_name": "alice-laptop",
                        "expires_at": "2025-02-10T10:00:00Z",
                    }
                }
            },
        },
        401: {
            "description": "Invalid master token",
            "content": {
                "application/json": {"example": {"detail": "Invalid master token"}}
            },
        },
    },
)
async def register_client(request: RegisterRequest) -> RegisterResponse:
    """
    Register a new client and receive a session token.

    **Flow**:
    1. Client provides a unique name (e.g., 'alice-laptop', 'ci-runner-1')
    2. Client authenticates with master token
    3. Server returns a session token valid for 7 days

    **Usage**:
    After registration, use the session_token for all API calls:
    ```bash
    curl http://localhost:8000/me \\
      -H "Authorization: Bearer <session_token>"
    ```

    **CLI Registration**:
    ```bash
    olav register --name "my-laptop" --server http://localhost:8000
    ```
    """
    # Validate master token
    is_valid, _ = validate_token(request.master_token)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid master token",
        )

    # Create session with specified role
    session = create_session(request.client_name, role=request.role)
    logger.info(f"Client registered: {request.client_name} (id: {session.client_id}, role: {session.role.value})")

    return RegisterResponse(
        session_token=session.token,
        client_id=session.client_id,
        client_name=session.client_name,
        role=session.role,
        expires_at=session.expires_at,
    )


@router.get(
    "/auth/sessions",
    summary="List active client sessions (admin)",
    responses={
        200: {
            "description": "List of active sessions",
            "content": {
                "application/json": {
                    "example": {
                        "sessions": [
                            {
                                "client_id": "550e8400-e29b-41d4-a716-446655440000",
                                "client_name": "alice-laptop",
                                "created_at": "2025-01-27T10:00:00Z",
                                "expires_at": "2025-02-03T10:00:00Z",
                            }
                        ],
                        "total": 1,
                    }
                }
            },
        },
    },
)
async def list_client_sessions(current_user: CurrentUser):
    """
    List all active client sessions.

    Only accessible with master token (for admin purposes).
    """
    sessions = get_active_sessions()
    return {
        "sessions": [
            {
                "client_id": s.client_id,
                "client_name": s.client_name,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.post(
    "/auth/revoke/{session_token}",
    summary="Revoke a client session token",
    responses={
        200: {
            "description": "Session revoked",
            "content": {
                "application/json": {"example": {"success": True, "message": "Session revoked"}}
            },
        },
        404: {
            "description": "Session not found",
            "content": {
                "application/json": {"example": {"detail": "Session not found"}}
            },
        },
    },
)
async def revoke_client_session(session_token: str, current_user: CurrentUser):
    """
    Revoke a session token.

    Use this to invalidate a compromised or no-longer-needed session.
    """
    success = revoke_session(session_token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return {"success": True, "message": "Session revoked"}
