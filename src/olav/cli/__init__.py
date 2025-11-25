"""OLAV CLI Client Module.

Provides remote and local execution modes for OLAV workflows.
"""

from .auth import (
    AuthClient,
    CredentialsManager,
    login_interactive,
    logout_interactive,
    whoami_interactive,
)
from .client import ExecutionResult, OLAVClient, ServerConfig, create_client

__all__ = [
    "AuthClient",
    "CredentialsManager",
    "ExecutionResult",
    "OLAVClient",
    "ServerConfig",
    "create_client",
    "login_interactive",
    "logout_interactive",
    "whoami_interactive",
]
