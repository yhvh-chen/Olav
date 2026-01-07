"""
OLAV v0.8 Configuration Settings

Uses Pydantic Settings to load configuration from:
1. Environment variables (.env file)
2. Default values defined in this file
"""

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# =============================================================================
# Project Paths
# =============================================================================

# Use absolute path to find project root
# Navigate up: config/ -> project_root/
import os as _os
_this_file = _os.path.abspath(__file__)
_config_dir = _os.path.dirname(_this_file)
_project_root = _os.path.dirname(_config_dir)

PROJECT_ROOT = Path(_project_root)
ENV_FILE = PROJECT_ROOT / ".env"
OLAV_DIR = PROJECT_ROOT / ".olav"
DATA_DIR = PROJECT_ROOT / "data"

# Load .env file first
load_dotenv(ENV_FILE)

# Ensure environment variables are properly set for pydantic-settings
# This fixes issues where old values might be cached
import os
if not os.getenv('LLM_PROVIDER'):
    os.environ['LLM_PROVIDER'] = 'openai'
if not os.getenv('EMBEDDING_PROVIDER'):
    os.environ['EMBEDDING_PROVIDER'] = 'openai'
if not os.getenv('OLAV_MODE'):
    os.environ['OLAV_MODE'] = 'QuickTest'


# =============================================================================
# Settings Classes
# =============================================================================

class Settings(BaseSettings):
    """OLAV Configuration Settings"""

    model_config = SettingsConfigDict(
        # Don't use env_file since load_dotenv is called at module level
        # env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # LLM Configuration
    # =========================================================================
    llm_provider: Literal["openai", "ollama", "azure"] = "openai"
    llm_api_key: str = ""
    llm_model_name: str = "gpt-4-turbo"
    llm_base_url: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # =========================================================================
    # Embedding Configuration
    # =========================================================================
    embedding_provider: Literal["openai", "ollama"] = "openai"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""

    # =========================================================================
    # Database Configuration
    # =========================================================================
    # DuckDB: Capability library (OLAP - analytical queries)
    #   Stores: CLI commands, APIs, NETCONF capabilities
    duckdb_path: str = str(OLAV_DIR / "capabilities.db")
    
    # SQLite: Agent session persistence (OLTP - transactional queries)
    #   Stores: DeepAgents checkpoints, conversation history
    #   Used in production mode; development uses in-memory storage
    checkpoint_db_path: str = str(OLAV_DIR / "checkpoints.db")

    # =========================================================================
    # Network Device Configuration
    # =========================================================================
    netbox_url: str = ""
    netbox_token: str = ""
    netbox_verify_ssl: bool = True
    netbox_device_tag: str = "olav-managed"

    device_username: str = "admin"
    device_password: str = ""
    device_enable_password: str = ""
    device_timeout: int = 30

    # =========================================================================
    # Network Execution Configuration
    # =========================================================================
    nornir_ssh_port: int = 22
    
    # NETCONF support planned for Phase 2+
    # netconf_port: int = 830  # Uncomment when NETCONF is needed

    # =========================================================================
    # Application Settings
    # =========================================================================
    # Use 'environment' field for runtime context (local/development/production)
    # Removed 'olav_mode' - this was v0.5 legacy; environment provides clearer semantics
    environment: Literal["local", "development", "production"] = "local"

    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Logging
    log_level: str = "INFO"
    
    # Network relevance guard - filters out non-network queries
    guard_enabled: bool = True

    # =========================================================================
    # Security & Authentication
    # =========================================================================
    auth_disabled: bool = True
    token_max_age_hours: int = 24
    session_token_max_age_hours: int = 168
    olav_api_token: str = ""
    log_format: Literal["json", "text"] = "text"

    # =========================================================================
    # Optional Services (Removed in v0.8)
    # =========================================================================
    # OpenSearch, Redis, and other external services are NOT used in v0.8
    # All caching is done via DuckDB locally
    # These fields are kept for reference only and will be removed in future

    # =========================================================================
    # Development Settings
    # =========================================================================
    use_dynamic_router: bool = True
    langsmith_api_key: str = ""  # Optional for debugging
    langsmith_project: str = "olav-v0.8"
    debug: bool = False

    # =========================================================================
    # Validators (Removed)
    # =========================================================================
    # postgres_uri validator removed - not needed in v0.8
    # All database operations use DuckDB via duckdb_path


# =============================================================================
# Singleton Instance
# =============================================================================

# Lazy initialization - will be initialized on first access
_settings = None


def get_settings() -> Settings:
    """Get or create the settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# For backward compatibility - will trigger lazy initialization on import
try:
    settings = get_settings()
except Exception as e:
    # If loading fails, provide a helpful error message
    print(f"Error loading settings: {e}")
    print("Please ensure .env file exists in the project root with proper values")
    raise

