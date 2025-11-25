"""JWT Authentication and RBAC for OLAV API Server.

Provides:
- JWT token generation and validation
- User model and password hashing
- RBAC (Role-Based Access Control) dependency injection
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ============================================
# Configuration
# ============================================
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "olav-dev-secret-change-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))

# Password hashing - using pbkdf2_sha256 instead of bcrypt (avoids 72-byte limit issues)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class CustomHTTPBearer(HTTPBearer):
    """HTTPBearer subclass that maps missing credentials (default 403) to 401.

    FastAPI's default HTTPBearer raises 403 for missing Authorization header.
    Tests and conventional API semantics expect 401 Unauthorized instead.
    """

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:  # type: ignore[override]
        try:
            return await super().__call__(request)
        except HTTPException as exc:  # Map 'Not authenticated' 403 to 401
            if (
                exc.status_code == status.HTTP_403_FORBIDDEN
                and str(exc.detail).lower() == "not authenticated"
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            raise


# HTTP Bearer token scheme (customized)
security = CustomHTTPBearer()


# ============================================
# Data Models
# ============================================
class User(BaseModel):
    """User model with role-based permissions."""

    username: str
    role: Literal["admin", "operator", "viewer"] = "viewer"
    disabled: bool = False


class TokenData(BaseModel):
    """JWT token payload."""

    username: str
    role: str


class Token(BaseModel):
    """API response for login endpoint."""

    access_token: str
    token_type: str = "bearer"


# ============================================
# In-Memory User Database (Demo)
# ============================================
# TODO: Replace with PostgreSQL/Redis in production
# Password hashes generated with pbkdf2_sha256 (avoids bcrypt 72-byte limit)
FAKE_USERS_DB = {
    "admin": {
        "username": "admin",
        # Password: admin123
        "hashed_password": "$pbkdf2-sha256$29000$8J4TovT.vzfmfK81Zqw1xg$JR7l3nIu2/0ntfi89BTB58IccchYFgGAoniBJZq73lo",
        "role": "admin",
        "disabled": False,
    },
    "operator": {
        "username": "operator",
        # Password: operator123
        "hashed_password": "$pbkdf2-sha256$29000$C2HM.b/XOocQAqCUEiIE4A$3rgnacNNJDHMhObafjNdG2NLaOF8MVYhRNPhaWOeVl4",
        "role": "operator",
        "disabled": False,
    },
    "viewer": {
        "username": "viewer",
        # Password: viewer123
        "hashed_password": "$pbkdf2-sha256$29000$iNF6T.k9J2RMiTEmJGSsNQ$uBUeBJr1die7gU3FWsp8zaMaOdLNQ57BkaoSycG1bPI",
        "role": "viewer",
        "disabled": False,
    },
}


# ============================================
# Password Utilities
# ============================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash plaintext password."""
    return pwd_context.hash(password)


# ============================================
# User Authentication
# ============================================
def get_user(username: str) -> User | None:
    """Retrieve user from database."""
    if username in FAKE_USERS_DB:
        user_dict = FAKE_USERS_DB[username]
        return User(**user_dict)
    return None


def authenticate_user(username: str, password: str) -> User | None:
    """Authenticate user with username/password."""
    user_dict = FAKE_USERS_DB.get(username)
    if not user_dict:
        return None
    if not verify_password(password, user_dict["hashed_password"]):
        return None
    return User(**user_dict)


# ============================================
# JWT Token Operations
# ============================================
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Generate JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if username is None or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return TokenData(username=username, role=role)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {e}",
        ) from e


# ============================================
# FastAPI Dependencies
# ============================================
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    """Dependency: Extract and validate current user from JWT token."""
    token = credentials.credentials
    token_data = decode_access_token(token)

    user = get_user(username=token_data.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return user


async def require_role(
    required_role: Literal["admin", "operator", "viewer"],
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency factory: Require specific role for endpoint access."""
    role_hierarchy = {"viewer": 1, "operator": 2, "admin": 3}

    if role_hierarchy[current_user.role] < role_hierarchy[required_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {required_role}",
        )
    return current_user


# ============================================
# Convenience Dependencies
# ============================================
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(lambda u=Depends(get_current_user): require_role("admin", u))]
OperatorUser = Annotated[
    User, Depends(lambda u=Depends(get_current_user): require_role("operator", u))
]
