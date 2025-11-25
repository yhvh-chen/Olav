"""Environment settings - loads sensitive data from .env file.

This module ONLY handles sensitive credentials and environment-specific overrides.
Application configuration is in config/settings.py.
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: src/olav/core/settings.py -> src/olav/core/ -> src/olav/ -> src/ -> project_root/
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

# Debug: print path resolution
if not ENV_FILE_PATH.exists():
    import sys

    print(f"Warning: .env file not found at {ENV_FILE_PATH.absolute()}", file=sys.stderr)
    print(f"Settings file location: {Path(__file__).absolute()}", file=sys.stderr)


class EnvSettings(BaseSettings):
    """Environment variables for sensitive data and Docker configuration."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============================================
    # LLM API Keys
    # ============================================
    llm_provider: Literal["openai", "ollama", "azure"] = "openai"
    llm_api_key: str = ""
    llm_model_name: str = "gpt-4-turbo"  # Allow override

    # ============================================
    # Infrastructure Credentials
    # ============================================
    # PostgreSQL
    postgres_user: str = "olav"
    postgres_password: str = "OlavPG123!"
    postgres_db: str = "olav"
    postgres_uri: str = ""  # Auto-built if empty

    # OpenSearch (Docker env vars)
    opensearch_url: str = ""  # Auto-built if empty
    disable_security_plugin: str = "true"
    opensearch_java_opts: str = "-Xms512m -Xmx512m"

    # Redis
    redis_url: str = ""  # Auto-built if empty

    # ============================================
    # NetBox Integration
    # ============================================
    netbox_url: str = ""
    netbox_token: str = ""

    # ============================================
    # Device Credentials
    # ============================================
    device_username: str = "cisco"
    device_password: str = "cisco"

    # ============================================
    # Runtime Environment Detection
    # ============================================
    environment: Literal["local", "docker"] = "local"

    def __init__(self, **kwargs) -> None:
        """Initialize and auto-detect environment."""
        super().__init__(**kwargs)

        # Auto-detect Docker environment
        import os

        if os.path.exists("/.dockerenv"):
            self.environment = "docker"

        # Auto-build URIs if not provided
        # Graceful import of config.settings with fallback stub for tests/minimal environments
        try:  # pragma: no cover - defensive branch
            from config.settings import InfrastructureConfig  # type: ignore
        except Exception:  # pragma: no cover

            class InfrastructureConfig:  # minimal fallback
                POSTGRES_HOST_DOCKER = "postgres"
                POSTGRES_PORT_DOCKER = 5432
                POSTGRES_HOST_LOCAL = "localhost"
                POSTGRES_PORT_LOCAL = 55432
                OPENSEARCH_HOST_DOCKER = "opensearch"
                OPENSEARCH_PORT_DOCKER = 9200
                OPENSEARCH_HOST_LOCAL = "localhost"
                OPENSEARCH_PORT_LOCAL = 9200
                REDIS_HOST_DOCKER = "redis"
                REDIS_PORT_DOCKER = 6379
                REDIS_HOST_LOCAL = "localhost"
                REDIS_PORT_LOCAL = 6379
                POSTGRES_DB = "olav"

                @classmethod
                def get_postgres_uri(cls, host: str, port: int, user: str, password: str) -> str:
                    return f"postgresql://{user}:{password}@{host}:{port}/{cls.POSTGRES_DB}"

                @classmethod
                def get_opensearch_url(cls, host: str, port: int) -> str:
                    return f"http://{host}:{port}"

                @classmethod
                def get_redis_url(cls, host: str, port: int) -> str:
                    return f"redis://{host}:{port}"

        if not self.postgres_uri:
            host = (
                InfrastructureConfig.POSTGRES_HOST_DOCKER
                if self.environment == "docker"
                else InfrastructureConfig.POSTGRES_HOST_LOCAL
            )
            port = (
                InfrastructureConfig.POSTGRES_PORT_DOCKER
                if self.environment == "docker"
                else InfrastructureConfig.POSTGRES_PORT_LOCAL
            )
            self.postgres_uri = InfrastructureConfig.get_postgres_uri(
                host, port, self.postgres_user, self.postgres_password
            )

        if not self.opensearch_url:
            host = (
                InfrastructureConfig.OPENSEARCH_HOST_DOCKER
                if self.environment == "docker"
                else InfrastructureConfig.OPENSEARCH_HOST_LOCAL
            )
            port = (
                InfrastructureConfig.OPENSEARCH_PORT_DOCKER
                if self.environment == "docker"
                else InfrastructureConfig.OPENSEARCH_PORT_LOCAL
            )
            self.opensearch_url = InfrastructureConfig.get_opensearch_url(host, port)

        if not self.redis_url:
            host = (
                InfrastructureConfig.REDIS_HOST_DOCKER
                if self.environment == "docker"
                else InfrastructureConfig.REDIS_HOST_LOCAL
            )
            port = (
                InfrastructureConfig.REDIS_PORT_DOCKER
                if self.environment == "docker"
                else InfrastructureConfig.REDIS_PORT_LOCAL
            )
            self.redis_url = InfrastructureConfig.get_redis_url(host, port)


settings = EnvSettings()
