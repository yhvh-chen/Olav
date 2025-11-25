"""OLAV CLI Authentication Manager.

Handles JWT token storage, login/logout commands, and automatic token refresh.

Architecture:
    ~/.olav/credentials (JSON file):
        {
            "server_url": "http://localhost:8000",
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
            "token_type": "bearer",
            "expires_at": "2025-11-24T12:00:00",
            "username": "admin"
        }

Security:
    - Credentials file permissions: 0600 (user-only read/write)
    - Tokens stored in plaintext (JWT is already signed, encryption overkill for CLI)
    - Warning if file permissions are too permissive
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from pydantic import BaseModel
from rich.console import Console
from rich.prompt import Prompt

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
    )

logger = logging.getLogger(__name__)


# ============================================
# Data Models
# ============================================
class Credentials(BaseModel):
    """Stored authentication credentials."""

    server_url: str
    access_token: str
    token_type: str = "bearer"
    expires_at: str  # ISO 8601 format
    username: str


class LoginResponse(BaseModel):
    """Response from /auth/login endpoint."""

    access_token: str
    token_type: str
    expires_in: int  # seconds


# ============================================
# Credentials Manager
# ============================================
class CredentialsManager:
    """Manage stored authentication credentials."""

    def __init__(self, credentials_path: Path | None = None) -> None:
        """
        Initialize credentials manager.

        Args:
            credentials_path: Custom path to credentials file (default: ~/.olav/credentials)
        """
        if credentials_path is None:
            home = Path.home()
            olav_dir = home / ".olav"
            olav_dir.mkdir(exist_ok=True)
            credentials_path = olav_dir / "credentials"

        self.credentials_path = credentials_path
        self.console = Console()

    def load(self) -> Credentials | None:
        """
        Load credentials from file.

        Returns:
            Credentials if file exists and valid, None otherwise
        """
        if not self.credentials_path.exists():
            logger.debug(f"Credentials file not found: {self.credentials_path}")
            return None

        try:
            # Check file permissions (Unix only)
            if sys.platform != "win32":
                stat_info = self.credentials_path.stat()
                if stat_info.st_mode & 0o077:  # Check if group/other have permissions
                    self.console.print(
                        f"[yellow]⚠️  Warning: Credentials file {self.credentials_path} has "
                        f"insecure permissions. Run: chmod 600 {self.credentials_path}[/yellow]"
                    )

            with open(self.credentials_path, encoding="utf-8") as f:
                data = json.load(f)

            creds = Credentials(**data)

            # Check if token is expired
            expires_at = datetime.fromisoformat(creds.expires_at)
            if datetime.now() > expires_at:
                logger.info("Token expired, credentials will be refreshed")
                return None

            return creds

        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.error(f"Failed to load credentials: {e}")
            return None

    def save(self, credentials: Credentials) -> None:
        """
        Save credentials to file.

        Args:
            credentials: Credentials to save
        """
        try:
            # Ensure directory exists
            self.credentials_path.parent.mkdir(parents=True, exist_ok=True)

            # Write credentials
            with open(self.credentials_path, "w", encoding="utf-8") as f:
                json.dump(credentials.model_dump(), f, indent=2)

            # Set file permissions (Unix only)
            if sys.platform != "win32":
                os.chmod(self.credentials_path, 0o600)  # User read/write only

            logger.info(f"Credentials saved to {self.credentials_path}")

        except OSError as e:
            logger.error(f"Failed to save credentials: {e}")
            raise

    def delete(self) -> None:
        """Delete credentials file."""
        if self.credentials_path.exists():
            self.credentials_path.unlink()
            logger.info(f"Credentials deleted: {self.credentials_path}")

    def is_token_expiring_soon(self, credentials: Credentials, threshold_minutes: int = 5) -> bool:
        """
        Check if token will expire soon.

        Args:
            credentials: Credentials to check
            threshold_minutes: Consider "soon" if expires within this many minutes

        Returns:
            True if token expires within threshold
        """
        expires_at = datetime.fromisoformat(credentials.expires_at)
        return datetime.now() + timedelta(minutes=threshold_minutes) > expires_at


# ============================================
# Authentication Client
# ============================================
class AuthClient:
    """Client for authentication operations."""

    def __init__(
        self, server_url: str, credentials_manager: CredentialsManager | None = None
    ) -> None:
        """
        Initialize auth client.

        Args:
            server_url: API server base URL
            credentials_manager: Credentials manager (default: create new)
        """
        self.server_url = server_url.rstrip("/")
        self.credentials_manager = credentials_manager or CredentialsManager()
        self.console = Console()

    async def login(self, username: str, password: str) -> Credentials:
        """
        Authenticate with server and store credentials.

        Args:
            username: Username
            password: Password

        Returns:
            Stored credentials

        Raises:
            httpx.HTTPStatusError: If authentication fails
            ConnectionError: If server is unreachable
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/auth/login",
                    data={"username": username, "password": password},
                    timeout=10.0,
                )
                response.raise_for_status()

            login_resp = LoginResponse(**response.json())

            # Calculate expiration time
            expires_at = datetime.now() + timedelta(seconds=login_resp.expires_in)

            # Create credentials
            credentials = Credentials(
                server_url=self.server_url,
                access_token=login_resp.access_token,
                token_type=login_resp.token_type,
                expires_at=expires_at.isoformat(),
                username=username,
            )

            # Save credentials
            self.credentials_manager.save(credentials)

            self.console.print(f"[green]✅ Successfully logged in as {username}[/green]")
            self.console.print(f"   Server: {self.server_url}")
            self.console.print(f"   Token expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}")

            return credentials

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                msg = "Invalid username or password"
                raise ValueError(msg) from e
            raise

        except httpx.RequestError as e:
            msg = f"Cannot connect to server: {self.server_url}"
            raise ConnectionError(msg) from e

    async def logout(self) -> None:
        """
        Logout by deleting stored credentials.

        Note: JWT tokens are stateless, so server-side logout is not needed.
        """
        self.credentials_manager.delete()
        self.console.print("[green]✅ Successfully logged out[/green]")
        self.console.print(
            f"   Credentials removed from {self.credentials_manager.credentials_path}"
        )

    async def refresh_token_if_needed(self, credentials: Credentials) -> Credentials:
        """
        Refresh token if it's expiring soon.

        Args:
            credentials: Current credentials

        Returns:
            Refreshed credentials (or original if not needed)

        Note: Current implementation doesn't support refresh tokens.
              In production, add /auth/refresh endpoint.
        """
        if self.credentials_manager.is_token_expiring_soon(credentials):
            logger.warning("Token expiring soon, but refresh not implemented. Re-login required.")
            self.console.print(
                "[yellow]⚠️  Your token is expiring soon. Please run 'olav login' again.[/yellow]"
            )

        return credentials

    def get_auth_header(self, credentials: Credentials) -> dict[str, str]:
        """
        Get Authorization header for API requests.

        Args:
            credentials: Credentials

        Returns:
            Dict with Authorization header
        """
        return {"Authorization": f"{credentials.token_type} {credentials.access_token}"}


# ============================================
# Interactive Login/Logout Commands
# ============================================
async def login_interactive(server_url: str | None = None) -> Credentials:
    """
    Interactive login command.

    Args:
        server_url: Server URL (default: prompt user or use env OLAV_SERVER_URL)

    Returns:
        Stored credentials
    """
    console = Console()

    # Determine server URL
    if server_url is None:
        default_url = os.getenv("OLAV_SERVER_URL", "http://localhost:8000")
        server_url = Prompt.ask("Server URL", default=default_url)

    # Get credentials
    username = Prompt.ask("Username")
    password = Prompt.ask("Password", password=True)

    # Authenticate
    auth_client = AuthClient(server_url)

    try:
        return await auth_client.login(username, password)

    except ValueError as e:
        console.print(f"[red]❌ Authentication failed: {e}[/red]")
        raise

    except ConnectionError as e:
        console.print(f"[red]❌ Connection failed: {e}[/red]")
        console.print("\n💡 Tips:")
        console.print("   1. Check if server is running: docker-compose up -d olav-server")
        console.print("   2. Verify server URL is correct")
        raise


async def logout_interactive() -> None:
    """Interactive logout command."""
    auth_client = AuthClient(server_url="")  # Server URL not needed for logout
    await auth_client.logout()


async def whoami_interactive() -> None:
    """Show current authentication status."""
    console = Console()
    creds_manager = CredentialsManager()

    credentials = creds_manager.load()

    if credentials is None:
        console.print("[yellow]Not authenticated[/yellow]")
        console.print("\n💡 Run: olav login")
        return

    # Check expiration
    expires_at = datetime.fromisoformat(credentials.expires_at)
    time_remaining = expires_at - datetime.now()

    if time_remaining.total_seconds() <= 0:
        console.print("[red]❌ Token expired[/red]")
        console.print("\n💡 Run: olav login")
        return

    console.print("[green]✅ Authenticated[/green]")
    console.print(f"   Username: {credentials.username}")
    console.print(f"   Server: {credentials.server_url}")
    console.print(f"   Expires in: {int(time_remaining.total_seconds() / 60)} minutes")

    if time_remaining.total_seconds() < 300:  # Less than 5 minutes
        console.print("\n[yellow]⚠️  Token expiring soon, consider re-authenticating[/yellow]")
