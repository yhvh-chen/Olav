# -*- coding: utf-8 -*-
"""
OLAV Unified Configuration - Single Source of Truth
====================================================

Usage:
1. Copy .env.example to .env and configure your credentials
2. All settings load from .env file
3. Use config classes for default values that rarely change

Priority:
1. Environment variables (highest priority)
2. .env file values
3. Default values in this file
"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# =============================================================================
# Project Root Detection
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"


# =============================================================================
# Environment Settings (loads from .env)
# =============================================================================

class EnvSettings(BaseSettings):
    """Environment-based configuration loaded from .env file.
    
    All sensitive credentials and runtime configurations should be set here.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # LLM Configuration
    # =========================================================================
    llm_provider: Literal["openai", "ollama", "azure"] = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model_name: str = "gpt-4-turbo"
    llm_fast_model: str = "gpt-3.5-turbo"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # =========================================================================
    # Embedding Configuration
    # =========================================================================
    embedding_provider: Literal["openai", "ollama"] = "ollama"
    embedding_api_key: str = ""
    embedding_base_url: str = "http://host.docker.internal:11434"
    embedding_model: str = "nomic-embed-text:latest"
    embedding_dimensions: int = 768

    # =========================================================================
    # PostgreSQL (LangGraph Checkpointer)
    # =========================================================================
    postgres_host: str = "localhost"
    postgres_port: int = 55432
    postgres_user: str = "olav"
    postgres_password: str = ""
    postgres_db: str = "olav"
    postgres_uri: str = ""  # If empty, built from other fields at init

    @model_validator(mode="after")
    def build_postgres_uri(self) -> "EnvSettings":
        """Build postgres_uri from fields if not explicitly set."""
        if not self.postgres_uri:
            self.postgres_uri = f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        return self

    # =========================================================================
    # OpenSearch
    # =========================================================================
    opensearch_host: str = "localhost"
    opensearch_port: int = 19200
    opensearch_username: str = ""
    opensearch_password: str = ""
    opensearch_verify_certs: bool = False
    opensearch_index_prefix: str = "olav"
    opensearch_url: str = ""

    @model_validator(mode="after")
    def build_opensearch_url(self) -> "EnvSettings":
        """Build OpenSearch URL if not set."""
        if not self.opensearch_url:
            self.opensearch_url = f"http://{self.opensearch_host}:{self.opensearch_port}"
        return self

    # =========================================================================
    # Redis
    # =========================================================================
    # Redis is OPTIONAL in this project (compose uses it behind a profile).
    # If not explicitly configured, leave redis_url empty and fall back to in-memory cache.
    redis_url: str = ""  # Preferred: set REDIS_URL=redis://olav-redis:6379
    redis_host: str = "localhost"  # Used only when explicitly provided via env
    redis_port: int = 6379
    redis_password: str = ""

    @model_validator(mode="after")
    def build_redis_url(self) -> "EnvSettings":
        """Build redis_url only when Redis config is explicitly provided.

        This avoids accidental localhost:6379 connections in environments where Redis
        isn't running (QuickTest, Windows host CLI, default docker-compose without cache profile).
        """
        if self.redis_url:
            return self

        fields_set = getattr(self, "model_fields_set", set())
        if any(k in fields_set for k in ("redis_host", "redis_port", "redis_password")):
            if self.redis_password:
                self.redis_url = f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
            else:
                self.redis_url = f"redis://{self.redis_host}:{self.redis_port}"

        return self

    # =========================================================================
    # NetBox (Single Source of Truth for Inventory)
    # =========================================================================
    netbox_url: str = ""
    netbox_token: str = ""
    netbox_verify_ssl: bool = True

    # =========================================================================
    # Device Credentials
    # =========================================================================
    device_username: str = ""
    device_password: str = ""
    device_enable_password: str = ""

    # =========================================================================
    # Environment
    # =========================================================================
    environment: Literal["local", "development", "production"] = "local"

    # OLAV runtime mode (used for safe defaults)
    olav_mode: Literal["QuickTest", "Production"] = "QuickTest"

    @field_validator("olav_mode", mode="before")
    @classmethod
    def normalize_olav_mode(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        if normalized in ("quicktest", "quick", "test", "dev", "development", "local"):
            return "QuickTest"
        if normalized in ("production", "prod"):
            return "Production"

        return value

    # =========================================================================
    # API Server
    # =========================================================================
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    cors_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"
    api_rate_limit_rpm: int = 60
    api_rate_limit_enabled: bool = False

    # =========================================================================
    # Authentication
    # =========================================================================
    token_max_age_hours: int = 24
    session_token_max_age_hours: int = 168
    auth_disabled: bool = False
    olav_api_token: str = ""  # Master token (OLAV_API_TOKEN)

    @model_validator(mode="after")
    def apply_mode_defaults(self) -> "EnvSettings":
        """Apply safe defaults derived from OLAV mode.

        Note: explicit env vars still win (env_file + environment have higher priority).
        """
        fields_set = getattr(self, "model_fields_set", set())

        # Default auth behavior: QuickTest disables auth; Production enables auth.
        # Only apply if auth_disabled wasn't explicitly set.
        if "auth_disabled" not in fields_set:
            self.auth_disabled = self.olav_mode == "QuickTest"

        return self

    # =========================================================================
    # WebSocket
    # =========================================================================
    websocket_heartbeat_interval: int = 30
    websocket_max_connections: int = 100

    # =========================================================================
    # Feature Flags
    # =========================================================================
    expert_mode: bool = False
    use_dynamic_router: bool = True  # Enable DynamicIntentRouter
    enable_agentic_rag: bool = True
    enable_deep_dive_memory: bool = True
    stream_stateless: bool = True  # Enable streaming
    enable_guard_mode: bool = True
    enable_hitl: bool = True
    yolo_mode: bool = False  # Skip approval (dangerous, test only)

    # =========================================================================
    # Agent Configuration
    # =========================================================================
    agent_max_tool_calls: int = 10
    agent_tool_timeout: int = 30
    agent_memory_window: int = 10
    agent_max_reflections: int = 3
    agent_language: Literal["auto", "zh", "en"] = "auto"

    # =========================================================================
    # Diagnosis Configuration
    # =========================================================================
    diagnosis_max_iterations: int = 5
    diagnosis_confidence_threshold: float = 0.8
    diagnosis_methodology: Literal["funnel", "parallel"] = "funnel"

    # =========================================================================
    # LangSmith Tracing (optional)
    # =========================================================================
    langsmith_enabled: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "olav-dev"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # =========================================================================
    # Collector/Sandbox Configuration
    # =========================================================================
    collector_force_enable: bool = False
    collector_min_privilege: int = 15
    collector_blacklist_file: str = "command_blacklist.txt"
    collector_capture_diff: bool = True

    # =========================================================================
    # Paths (can be overridden via env vars)
    # =========================================================================
    suzieq_data_dir: str = "data/suzieq-parquet"
    suzieq_max_data_age_seconds: int = 7200
    documents_dir: str = "data/documents"
    reports_dir: str = "data/reports"
    inspection_reports_dir: str = "data/inspection-reports"
    cache_dir: str = "data/cache"
    logs_dir: str = "logs"
    prompts_dir: str = "config/prompts"
    inspections_dir: str = "config/inspections"

    # =========================================================================
    # Logging
    # =========================================================================
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file_enabled: bool = True
    log_file_path: str = "logs/olav.log"
    log_file_max_size_mb: int = 10
    log_file_backup_count: int = 5

    # =========================================================================
    # Inspection
    # =========================================================================
    inspection_enabled: bool = True
    inspection_parallel_devices: int = 5
    inspection_device_timeout: int = 120
    inspection_notify_on_critical: bool = True
    inspection_notify_on_complete: bool = True
    inspection_notify_on_failure: bool = True
    inspection_notify_webhook_url: str = ""

    # =========================================================================
    # Tool Configuration
    # =========================================================================
    nornir_num_workers: int = 10
    command_timeout: int = 30
    suzieq_timeout: int = 60

    # =========================================================================
    # LLM Retry Configuration
    # =========================================================================
    llm_max_retries: int = 3
    llm_retry_delay: float = 1.0
    llm_retry_backoff_multiplier: float = 2.0
    llm_retry_max_delay: float = 30.0


# =============================================================================
# Global Settings Instance
# =============================================================================

settings = EnvSettings()


# =============================================================================
# Path Helper Functions
# =============================================================================

def get_path(name: str) -> Path:
    """Get absolute path for a configured directory.
    
    Args:
        name: Path name (suzieq_data, documents, reports, cache, logs, prompts, inspections)
        
    Returns:
        Absolute path
    """
    paths_map = {
        "suzieq_data": settings.suzieq_data_dir,
        "documents": settings.documents_dir,
        "reports": settings.reports_dir,
        "inspection_reports": settings.inspection_reports_dir,
        "cache": settings.cache_dir,
        "logs": settings.logs_dir,
        "prompts": settings.prompts_dir,
        "inspections": settings.inspections_dir,
    }
    rel_path = paths_map.get(name)
    if rel_path is None:
        raise ValueError(f"Unknown path: {name}")
    return PROJECT_ROOT / rel_path


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Settings
    "EnvSettings",
    "settings",
    # Paths
    "PROJECT_ROOT",
    "ENV_FILE_PATH",
    "DATA_DIR",
    "CONFIG_DIR",
    "get_path",
]
