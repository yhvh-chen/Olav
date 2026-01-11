"""
OLAV v0.8 Configuration Settings

Three-layer configuration architecture (per DESIGN_V0.81.md §C.1-C.2):
- Layer 1: .env (sensitive + connection) - human-maintained, never commit to git
- Layer 2: .olav/settings.json (behavior + preferences) - user-editable, agent-readable
- Layer 3: This file (loader + defaults) - code implementation

Configuration Priority (high to low):
1. Environment variables (export LLM_MODEL_NAME=gpt-4o)
2. .env file (LLM_MODEL_NAME=gpt-4-turbo)
3. .olav/settings.json ({"model": "gpt-4o"})
4. Code defaults (llm_model_name: str = "gpt-4-turbo")

True Source of Truth:
- .env: Sensitive configuration (API Keys, passwords, tokens)
- .olav/settings.json: Agent behavior (model, temperature, routing, HITL)
- This file: Code defaults and validation only (NOT true source)
"""

import json
import os

# =============================================================================
# Project Paths
# =============================================================================
# Use absolute path to find project root
# Navigate up: config/ -> project_root/
import os as _os
import re
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
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
if not os.getenv("LLM_PROVIDER"):
    os.environ["LLM_PROVIDER"] = "openai"
if not os.getenv("EMBEDDING_PROVIDER"):
    os.environ["EMBEDDING_PROVIDER"] = "ollama"  # Default to Ollama (free local embeddings)
if not os.getenv("OLAV_MODE"):
    os.environ["OLAV_MODE"] = "QuickTest"


# =============================================================================
# Nested Configuration Classes (Pydantic v2)
# =============================================================================


class GuardSettings(BaseSettings):
    """Guard 意图过滤器配置"""

    enabled: bool = Field(default=True, description="是否启用 Guard 过滤")
    strict_mode: bool = Field(default=False, description="严格模式：只允许明确的网络运维请求")


class RoutingSettings(BaseSettings):
    """Skill 路由配置"""

    confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Skill 匹配置信度阈值"
    )
    fallback_skill: str = Field(default="quick-query", description="降级目标 Skill ID")


class HITLSettings(BaseSettings):
    """Human-in-the-Loop 配置"""

    require_approval_for_write: bool = Field(default=True, description="写操作是否需要审批")
    require_approval_for_skill_update: bool = Field(
        default=True, description="Skill/Knowledge 更新是否需要审批"
    )
    approval_timeout_seconds: int = Field(
        default=300, ge=10, le=3600, description="审批超时时间 (秒)"
    )


class ExecutionSettings(BaseSettings):
    """命令执行配置"""

    use_textfsm: bool = Field(default=True, description="是否使用 TextFSM 解析命令输出")
    textfsm_fallback_to_raw: bool = Field(
        default=True, description="TextFSM 解析失败时是否回退到原始文本"
    )
    enable_token_statistics: bool = Field(default=True, description="是否启用 token 统计")


class DiagnosisSettings(BaseSettings):
    """诊断模块配置"""

    macro_max_confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="宏观分析置信度上限"
    )
    micro_target_confidence: float = Field(
        default=0.9, ge=0.0, le=1.0, description="微观分析目标置信度"
    )
    max_diagnosis_iterations: int = Field(
        default=5, ge=1, le=20, description="单轮诊断最大迭代次数"
    )
    require_approval_for_micro_analysis: bool = Field(
        default=True, description="微观分析是否需要审批"
    )
    auto_approve_if_confidence_below: float = Field(
        default=0.5, ge=0.0, le=1.0, description="置信度低于此值时自动审批"
    )
    enable_web_search: bool = Field(
        default=True, description="诊断时是否启用联网搜索（fallback 模式）"
    )
    web_search_fallback_only: bool = Field(
        default=True, description="联网搜索仅在本地知识库无结果时启用"
    )
    web_search_max_results: int = Field(
        default=3, ge=1, le=10, description="每次网络搜索的最大结果数"
    )
    web_search_timeout: int = Field(
        default=10, ge=5, le=30, description="网络搜索超时时间（秒）"
    )


class LoggingSettings(BaseSettings):
    """日志配置"""

    level: str = Field(default="INFO", description="日志级别")
    audit_enabled: bool = Field(default=True, description="是否记录审计日志")


# =============================================================================
# Settings Classes
# =============================================================================


class Settings(BaseSettings):
    """OLAV Configuration Settings - Three-Layer Architecture

    This is NOT the true source of truth, but a loader with defaults:
    - Layer 1 (.env): True source for sensitive config (API Keys, passwords)
    - Layer 2 (.olav/settings.json): True source for agent behavior config
    - Layer 3 (this file): Code defaults and validation only

    Configuration Priority (high to low):
    1. Environment variables (export MY_VAR=value)
    2. .env file (MY_VAR=value)
    3. .olav/settings.json ({"myField": value})
    4. Code defaults (field: type = default_value)

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
    # Skill Configuration (Phase C-1)
    # =========================================================================
    enabled_skills: list[str] = Field(
        default_factory=list, description="启用的 Skill ID 列表 (空表示全部启用)"
    )
    disabled_skills: list[str] = Field(default_factory=list, description="禁用的 Skill ID 列表")

    # =========================================================================
    # Embedding Configuration (Phase 4: Knowledge Base Integration)
    # =========================================================================
    enable_embedding: bool = True
    embedding_provider: Literal["ollama", "openai", "none"] = (
        "ollama"  # Default to Ollama (free local)
    )
    embedding_model: str = "nomic-embed-text"  # Ollama model (768 dimensions)
    embedding_base_url: str = "http://localhost:11434"  # Ollama default URL
    embedding_api_key: str = ""  # Only needed for OpenAI embeddings

    # =========================================================================
    # Nested Configuration Objects (Phase C-1)
    # =========================================================================
    guard: GuardSettings = Field(default_factory=GuardSettings, description="Guard 过滤器配置")
    routing: RoutingSettings = Field(default_factory=RoutingSettings, description="Skill 路由配置")
    hitl: HITLSettings = Field(default_factory=HITLSettings, description="HITL 审批配置")
    diagnosis: DiagnosisSettings = Field(default_factory=DiagnosisSettings, description="诊断配置")
    execution: ExecutionSettings = Field(
        default_factory=ExecutionSettings, description="命令执行配置"
    )
    logging_settings: LoggingSettings = Field(
        default_factory=LoggingSettings, description="日志配置"
    )

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
        """Initialize settings and apply .olav/settings.json overrides (Layer 2)."""
        super().__init__(**kwargs)
        self._apply_olav_settings()

    def _apply_olav_settings(self) -> None:
        """Layer 2: Load and apply settings from .olav/settings.json.

        Priority: Environment variable > .env > .olav/settings.json > code defaults
        """
        settings_path = OLAV_DIR / "settings.json"
        if not settings_path.exists():
            return

        try:
            olav_settings = json.loads(settings_path.read_text(encoding="utf-8"))

            # Map JSON paths to Python attributes (simple fields)
            simple_mapping = {
                "model": "llm_model_name",
                "temperature": "llm_temperature",
                "enabledSkills": "enabled_skills",
                "disabledSkills": "disabled_skills",
            }

            # Get environment variable names for checking if explicitly set
            env_var_map = {
                "llm_model_name": "LLM_MODEL_NAME",
                "llm_temperature": "LLM_TEMPERATURE",
                "llm_max_tokens": "LLM_MAX_TOKENS",
                "guard_enabled": "GUARD_ENABLED",
                "log_level": "LOG_LEVEL",
            }

            # Apply simple field mappings
            for json_key, attr_name in simple_mapping.items():
                if json_key in olav_settings:
                    value = olav_settings[json_key]
                    # Only override if NOT already set by environment variable
                    env_var = env_var_map.get(attr_name)
                    if env_var and os.getenv(env_var):
                        continue  # Environment variable takes priority
                    setattr(self, attr_name, value)

            # Apply nested configuration mappings
            nested_mapping = {
                "guard": ("guard", GuardSettings),
                "routing": ("routing", RoutingSettings),
                "hitl": ("hitl", HITLSettings),
                "diagnosis": ("diagnosis", DiagnosisSettings),
                "execution": ("execution", ExecutionSettings),
                "logging": ("logging_settings", LoggingSettings),
            }

            for json_key, (attr_name, cls) in nested_mapping.items():
                if json_key in olav_settings:
                    nested_data = olav_settings[json_key]
                    if isinstance(nested_data, dict):
                        try:
                            # Convert camelCase keys to snake_case for Pydantic
                            converted_data = {}
                            for k, v in nested_data.items():
                                snake_key = self._camel_to_snake(k)
                                converted_data[snake_key] = v
                            # Create new nested object from converted JSON data
                            nested_obj = cls(**converted_data)
                            setattr(self, attr_name, nested_obj)
                        except Exception:
                            # If validation fails, keep default
                            pass

        except (json.JSONDecodeError, OSError):
            # Silently ignore invalid settings.json - use defaults
            pass

    @staticmethod
    def _camel_to_snake(name: str) -> str:
        """Convert camelCase to snake_case."""
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def to_dict(self) -> dict[str, Any]:
        """Export configuration as dictionary (for serialization)."""
        return self.model_dump()

    def save_to_json(self, path: Path | None = None) -> None:
        """Save configuration to JSON file.

        Args:
            path: Target file path. Defaults to .olav/settings.json
        """
        if path is None:
            path = OLAV_DIR / "settings.json"

        # Convert nested objects to dictionaries with camelCase keys
        def snake_to_camel(name: str) -> str:
            components = name.split("_")
            return components[0] + "".join(x.title() for x in components[1:])

        routing_dict = self.routing.model_dump()
        routing_dict_camel = {snake_to_camel(k): v for k, v in routing_dict.items()}

        hitl_dict = self.hitl.model_dump()
        hitl_dict_camel = {snake_to_camel(k): v for k, v in hitl_dict.items()}

        diagnosis_dict = self.diagnosis.model_dump()
        diagnosis_dict_camel = {snake_to_camel(k): v for k, v in diagnosis_dict.items()}

        data = {
            "model": self.llm_model_name,
            "temperature": self.llm_temperature,
            "enabledSkills": self.enabled_skills,
            "disabledSkills": self.disabled_skills,
            "guard": self.guard.model_dump(),
            "routing": routing_dict_camel,
            "hitl": hitl_dict_camel,
            "diagnosis": diagnosis_dict_camel,
            "logging": self.logging_settings.model_dump(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @field_validator("llm_model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate LLM model name."""
        if not v or len(v.strip()) == 0:
            raise ValueError("llm_model_name cannot be empty")
        return v.strip()

    @field_validator("llm_temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Validate LLM temperature parameter."""
        if not (0.0 <= v <= 2.0):
            raise ValueError("llm_temperature must be between 0.0 and 2.0")
        return v


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
