"""
OLAV v0.8 Configuration Settings

Three-layer configuration architecture (per DESIGN_V0.8.md §11.6):
- Layer 1: .env (sensitive + connection) - human-maintained, never commit to git
- Layer 2: .olav/settings.json (behavior + preferences) - user-editable, agent-readable
- Layer 3: This file (loader + defaults) - code implementation

Uses Pydantic Settings to load configuration from:
1. Environment variables (.env file) - Layer 1
2. .olav/settings.json - Layer 2
3. Default values defined in this file - Layer 3
"""

import json
import os

# =============================================================================
# Project Paths
# =============================================================================
# Use absolute path to find project root
# Navigate up: config/ -> project_root/
import os as _os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_this_file = _os.path.abspath(__file__)
_config_dir = _os.path.dirname(_this_file)
_project_root = _os.path.dirname(_config_dir)

PROJECT_ROOT = Path(_project_root)
ENV_FILE = PROJECT_ROOT / ".env"
OLAV_DIR = PROJECT_ROOT / ".olav"
DATA_DIR = PROJECT_ROOT / "data"

# Agent directory configuration (can be .olav, .claude, .cursor, etc.)
# Defaults to .olav for backward compatibility
# Can be overridden via AGENT_DIR environment variable
_agent_dir_name = os.getenv("AGENT_DIR", ".olav")
AGENT_DIR = PROJECT_ROOT / _agent_dir_name

# Load .env file first
load_dotenv(ENV_FILE)

# Ensure environment variables are properly set for pydantic-settings
# This fixes issues where old values might be cached
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
    """OLAV Configuration Settings
    
    Supports three-layer configuration:
    - Environment variables (highest priority)
    - .olav/settings.json (Layer 2)
    - Default values (lowest priority)
    """

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

    # Knowledge database: Vendor docs, team wiki, learned solutions
    knowledge_db_path: str = str(OLAV_DIR / "data" / "knowledge.db")

    # =========================================================================
    # Agent Configuration (Claude Code Compatibility)
    # =========================================================================
    # Agent directory name (e.g., .olav, .claude, .cursor)
    agent_dir: str = ".olav"
    agent_name: str = "OLAV"

    # Skills format: "auto" (detect), "legacy" (flat files), "claude-code" (SKILL.md)
    skill_format: Literal["auto", "legacy", "claude-code"] = "auto"

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
    # Skill Routing Configuration (from .olav/settings.json)
    # =========================================================================
    routing_confidence_threshold: float = 0.6
    routing_fallback_skill: str = "quick-query"

    # =========================================================================
    # Diagnosis Configuration (from .olav/settings.json)
    # =========================================================================
    diagnosis_macro_max_confidence: float = 0.7
    diagnosis_micro_target_confidence: float = 0.9
    diagnosis_max_iterations: int = 5

    # =========================================================================
    # Security & Authentication
    # =========================================================================
    auth_disabled: bool = True
    token_max_age_hours: int = 24
    session_token_max_age_hours: int = 168
    olav_api_token: str = ""
    log_format: Literal["json", "text"] = "text"

    # HITL Configuration
    # Master switch for Human-in-the-Loop - set ENABLE_HITL=false in .env for yolo mode
    enable_hitl: bool = True  # Reads from ENABLE_HITL env var
    hitl_require_approval_for_write: bool = True
    hitl_require_approval_for_skill_update: bool = True
    hitl_approval_timeout_seconds: int = 300

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

    def __init__(self, **kwargs):
        """Initialize settings and apply .olav/settings.json overrides."""
        super().__init__(**kwargs)
        self._apply_olav_settings()

    def _apply_olav_settings(self) -> None:
        """Layer 2: Load and apply settings from .olav/settings.json."""
        settings_path = OLAV_DIR / "settings.json"
        if not settings_path.exists():
            return

        try:
            olav_settings = json.loads(settings_path.read_text(encoding="utf-8"))

            # Map JSON paths to Python attributes
            mapping = {
                # LLM settings
                ("llm", "provider"): "llm_provider",
                ("llm", "model"): "llm_model_name",
                ("llm", "temperature"): "llm_temperature",
                ("llm", "max_tokens"): "llm_max_tokens",
                # Guard settings
                ("guard", "enabled"): "guard_enabled",
                # Routing settings
                ("routing", "confidenceThreshold"): "routing_confidence_threshold",
                ("routing", "fallbackSkill"): "routing_fallback_skill",
                # Diagnosis settings
                ("diagnosis", "macroMaxConfidence"): "diagnosis_macro_max_confidence",
                ("diagnosis", "microTargetConfidence"): "diagnosis_micro_target_confidence",
                ("diagnosis", "maxDiagnosisIterations"): "diagnosis_max_iterations",
                # HITL settings
                ("hitl", "requireApprovalForWrite"): "hitl_require_approval_for_write",
                ("hitl", "requireApprovalForSkillUpdate"): "hitl_require_approval_for_skill_update",
                ("hitl", "approvalTimeoutSeconds"): "hitl_approval_timeout_seconds",
                # Logging
                ("logging", "level"): "log_level",
            }

            # Get environment variable names for checking if explicitly set
            env_var_map = {
                "llm_provider": "LLM_PROVIDER",
                "llm_model_name": "LLM_MODEL_NAME",
                "llm_temperature": "LLM_TEMPERATURE",
                "llm_max_tokens": "LLM_MAX_TOKENS",
                "guard_enabled": "GUARD_ENABLED",
                "log_level": "LOG_LEVEL",
            }

            for json_path, attr_name in mapping.items():
                value = self._get_nested(olav_settings, json_path)
                if value is not None:
                    # Only override if NOT already set by environment variable
                    # Environment variables take priority over settings.json
                    env_var = env_var_map.get(attr_name)
                    if env_var and os.getenv(env_var):
                        # Environment variable is set, skip settings.json override
                        continue
                    setattr(self, attr_name, value)

        except (json.JSONDecodeError, OSError):
            # Silently ignore invalid settings.json - use defaults
            pass

    def _get_nested(self, d: dict, path: tuple) -> any:
        """Get nested value from dict using tuple path like ('llm', 'model')."""
        for key in path:
            if isinstance(d, dict) and key in d:
                d = d[key]
            else:
                return None
        return d


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

