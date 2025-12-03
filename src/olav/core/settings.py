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
    # Defaults sourced from config/settings.py LLMConfig for consistency
    llm_provider: Literal["openai", "ollama", "azure"] = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"  # OpenRouter by default
    llm_model_name: str = "x-ai/grok-4.1-fast:free"  # Grok 4.1 Fast (free) via OpenRouter

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
    # API Server Configuration
    # ============================================
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    
    # CORS Configuration (for WebGUI)
    # Comma-separated list of allowed origins, or "*" for all (dev only)
    cors_origins: str = "*"  # e.g., "http://localhost:3000,https://olav.company.com"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"  # e.g., "GET,POST,PUT,DELETE"
    cors_allow_headers: str = "*"
    
    # API Rate Limiting (requests per minute per user)
    api_rate_limit_rpm: int = 60
    api_rate_limit_enabled: bool = False  # Enable in production

    # ============================================
    # Token Authentication Configuration (Simplified)
    # ============================================
    # Token is auto-generated on server startup
    token_max_age_hours: int = 24  # Token valid for 24 hours
    # Disable authentication (for testing/development only!)
    auth_disabled: bool = False
    
    # WebSocket Configuration (for real-time streaming)
    websocket_heartbeat_interval: int = 30  # seconds
    websocket_max_connections: int = 100

    # ============================================
    # Gradio WebUI Authentication
    # ============================================
    ui_username: str = "admin"
    ui_password: str = "olav123"

    # ============================================
    # Feature Flags
    # ============================================
    expert_mode: bool = False
    use_dynamic_router: bool = True
    stream_stateless: bool = True

    # ============================================
    # LangSmith Tracing (Optional)
    # ============================================
    # Enable LangSmith for agent debugging and performance analysis
    # Set LANGSMITH_API_KEY in .env to enable
    langsmith_enabled: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "olav-dev"  # Project name in LangSmith
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # ============================================
    # Collector/Sandbox Configuration
    # ============================================
    collector_force_enable: bool = False
    collector_min_privilege: int = 15
    collector_blacklist_file: str = "command_blacklist.txt"
    collector_capture_diff: bool = True

    # ============================================
    # Agentic RAG Configuration
    # ============================================
    # Enable automatic saving of successful executions to episodic memory
    enable_agentic_rag: bool = True
    # Enable Deep Dive report auto-save to episodic memory
    enable_deep_dive_memory: bool = True

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
