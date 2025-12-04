"""OLAV Application Configuration Center.

This module defines all application settings including:
- Path configurations
- Network topology
- Agent configurations
- Tool parameters

Sensitive data (API keys, passwords) are loaded from .env via src.olav.core.settings
"""

from pathlib import Path
from typing import Literal

# Project structure
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

# ============================================
# Path Configuration
# ============================================
class Paths:
    """File and directory paths."""
    
    # Config files
    INVENTORY_CSV = CONFIG_DIR / "inventory.csv"
    PROMPTS_DIR = CONFIG_DIR / "prompts"
    INSPECTIONS_DIR = CONFIG_DIR / "inspections"
    CLI_BLACKLIST = CONFIG_DIR / "cli_blacklist.yaml"
    COMMAND_BLACKLIST = CONFIG_DIR / "command_blacklist.txt"
    
    # Data directories (runtime generated)
    SUZIEQ_PARQUET_DIR = DATA_DIR / "suzieq-parquet"
    DOCUMENTS_DIR = DATA_DIR / "documents"
    GENERATED_CONFIGS_DIR = DATA_DIR / "generated_configs"
    
    @classmethod
    def ensure_directories(cls):
        """Create all required directories."""
        for attr_name in dir(cls):
            if attr_name.isupper() and "DIR" in attr_name:
                path = getattr(cls, attr_name)
                if isinstance(path, Path):
                    path.mkdir(parents=True, exist_ok=True)


# ============================================
# LLM Configuration
# ============================================
class LLMConfig:
    """LLM provider settings (non-sensitive defaults).

    Adjusted to match legacy test expectations (MODEL_NAME == "gpt-4-turbo").
    New code should prefer dynamic model selection via `olav.core.settings`.
    """
    PROVIDER: Literal["openai", "ollama", "azure"] = "openai"
    BASE_URL: str = "https://openrouter.ai/api/v1"
    MODEL_NAME = "x-ai/grok-4.1-fast"
    TEMPERATURE = 0.2
    MAX_TOKENS = 16000
    
    # Fallback models for ModelFallbackMiddleware (LangChain 1.10)
    # Format: ["provider:model_name", ...] in priority order
    FALLBACK_MODELS: list[str] = ["openai:gpt-4o-mini"]


class EmbeddingConfig:
    """Embedding model settings for Agentic RAG.
    
    Note: OpenRouter does NOT support embeddings API.
    Use OpenAI direct API or local Ollama for embeddings.
    
    nomic-embed-text-v1.5: 768 dimensions (Matryoshka, can truncate to 512/256/128)
    """
    PROVIDER: Literal["openai", "ollama"] = "ollama"
    BASE_URL: str = "http://127.0.0.1:11434"  # Ollama local
    MODEL: str = "nomic-embed-text:latest"
    DIMENSIONS: int = 768  # nomic-embed-text native dimension


class VisionConfig:
    """Vision model settings for network diagram analysis.
    
    Used for:
    - Analyzing network topology screenshots
    - Understanding Visio/draw.io diagrams
    - Processing monitoring dashboard images
    """
    PROVIDER: Literal["openai", "ollama"] = "ollama"
    BASE_URL: str = "127.0.0.1:11434"  # OpenAI direct (not OpenRouter)
    MODEL: str = "llava:latest"  # GPT-4o has vision capabilities
    MAX_TOKENS: int = 4096


class LLMRetryConfig:
    """LLM retry/resilience settings (LangChain 1.10 Middleware).
    
    These settings configure ModelRetryMiddleware for automatic retry
    with exponential backoff on transient errors.
    """
    # Maximum retry attempts for transient errors
    MAX_RETRIES: int = 3
    
    # Exponential backoff settings
    BACKOFF_FACTOR: float = 2.0  # Multiplier for each retry
    INITIAL_DELAY: float = 1.0   # Initial delay in seconds
    MAX_DELAY: float = 60.0      # Maximum delay cap in seconds
    
    # Add randomness to prevent thundering herd
    JITTER: bool = True


class ToolRetryConfig:
    """Tool execution retry settings (for network tools).
    
    These settings configure retry behavior for SuzieQ, CLI, NETCONF tools
    when encountering transient network errors.
    """
    # Maximum retry attempts
    MAX_RETRIES: int = 3
    
    # Exponential backoff settings
    BACKOFF_FACTOR: float = 2.0
    INITIAL_DELAY: float = 1.0
    MAX_DELAY: float = 30.0  # Lower than LLM since network calls are faster
    
    # Add randomness to prevent thundering herd
    JITTER: bool = True


# ============================================
# Infrastructure Configuration
# ============================================
class InfrastructureConfig:
    """Infrastructure service endpoints (Docker container names)."""
    
    # Local development
    POSTGRES_HOST_LOCAL = "localhost"
    POSTGRES_PORT_LOCAL = 55432
    OPENSEARCH_HOST_LOCAL = "localhost"
    OPENSEARCH_PORT_LOCAL = 9200
    REDIS_HOST_LOCAL = "localhost"
    REDIS_PORT_LOCAL = 6379
    
    # Docker environment
    POSTGRES_HOST_DOCKER = "postgres"
    POSTGRES_PORT_DOCKER = 5432
    OPENSEARCH_HOST_DOCKER = "opensearch"
    OPENSEARCH_PORT_DOCKER = 9200
    REDIS_HOST_DOCKER = "redis"
    REDIS_PORT_DOCKER = 6379
    
    # Database
    POSTGRES_DB = "olav"
    
    @classmethod
    def get_postgres_uri(cls, host: str, port: int, user: str, password: str) -> str:
        """Build PostgreSQL connection URI."""
        return f"postgresql://{user}:{password}@{host}:{port}/{cls.POSTGRES_DB}"
    
    @classmethod
    def get_opensearch_url(cls, host: str, port: int) -> str:
        """Build OpenSearch URL."""
        return f"http://{host}:{port}"
    
    @classmethod
    def get_redis_url(cls, host: str, port: int) -> str:
        """Build Redis URL."""
        return f"redis://{host}:{port}"


# ============================================
# Agent Configuration
# ============================================
class AgentConfig:
    """DeepAgents orchestration settings."""
    
    MAX_ITERATIONS = 20
    ENABLE_HITL = True  # Human-in-the-Loop approval
    YOLO_MODE = False  # YOLO mode: skip all HITL approvals (dangerous!)
    
    # Language for workflow output (affects prompts and UI strings)
    # Supported: "zh" (Chinese), "en" (English), "ja" (Japanese)
    LANGUAGE: Literal["zh", "en", "ja"] = "zh"
    
    # SubAgent timeout (seconds)
    SUBAGENT_TIMEOUT = 300
    
    # Middleware settings
    ENABLE_TODO_LIST = True
    ENABLE_SUMMARIZATION = True
    SUMMARIZATION_THRESHOLD = 170_000  # tokens


# ============================================
# Inspection Configuration
# ============================================
class InspectionConfig:
    """Automated inspection settings."""
    
    # Enable scheduled inspection
    ENABLED = False  # Set to True to enable scheduled inspections
    
    # Schedule settings (cron-style)
    # Format: "HH:MM" for daily, or cron expression for complex schedules
    SCHEDULE_TIME = "09:00"  # Run at 9:00 AM daily
    SCHEDULE_CRON = None  # Optional: "0 9 * * *" (overrides SCHEDULE_TIME if set)
    SCHEDULE_INTERVAL_MINUTES = None  # Optional: Run every N minutes (for testing)
    
    # Default inspection profile to run
    DEFAULT_PROFILE = "daily_core_check"  # Profile name from config/inspections/
    
    # Output settings
    REPORTS_DIR = DATA_DIR / "inspection-reports"
    REPORT_FORMAT = "markdown"  # markdown, json, html
    KEEP_REPORTS_DAYS = 30  # Auto-cleanup reports older than N days
    
    # Notification (optional)
    NOTIFY_ON_FAILURE = True
    NOTIFY_WEBHOOK_URL: str | None = None  # Slack/Teams webhook for alerts
    
    # Execution settings
    PARALLEL_DEVICES = 10  # Max concurrent device checks
    TIMEOUT_PER_CHECK = 60  # seconds per check
    RETRY_FAILED_CHECKS = 1  # Number of retries for failed checks
    
    @classmethod
    def get_reports_dir(cls) -> "Path":
        """Ensure reports directory exists and return path."""
        cls.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        return cls.REPORTS_DIR


# ============================================
# Tool Configuration
# ============================================
class ToolConfig:
    """Tool-specific parameters."""
    
    # SuzieQ
    SUZIEQ_TABLES_LIMIT = 30  # Max tables to return in schema search
    SUZIEQ_QUERY_TIMEOUT = 30  # seconds
    
    # Nornir
    NORNIR_NUM_WORKERS = 100
    NORNIR_CONNECTION_TIMEOUT = 30
    
    # OpenConfig XPath
    OPENCONFIG_MAX_DEPTH = 10  # Max XPath depth
    
    # RAG
    RAG_TOP_K = 5  # Top K results
    RAG_SIMILARITY_THRESHOLD = 0.7


# ============================================
# Network Topology
# ============================================
class NetworkTopology:
    """Network device inventory and topology."""
    
    # Device roles (from inventory.csv)
    DEVICE_ROLES = ["core", "dist", "access"]
    
    # Platforms (Nornir platform keys)
    SUPPORTED_PLATFORMS = ["cisco_ios", "cisco_nxos", "arista_eos", "junos"]
    
    # Sites
    SITES = ["lab", "dc1", "branch-sh"]


# ============================================
# OpenSearch Index Configuration
# ============================================
class OpenSearchIndices:
    """OpenSearch index names and settings."""
    
    # Schema indices
    OPENCONFIG_SCHEMA = "openconfig-schema"
    SUZIEQ_SCHEMA = "suzieq-schema"
    
    # Memory indices
    EPISODIC_MEMORY = "olav-episodic-memory"
    
    # Document indices
    DOCUMENTS = "olav-docs"
    
    # Index settings
    NUM_SHARDS = 1
    NUM_REPLICAS = 0
    
    @classmethod
    def get_all_indices(cls) -> list[str]:
        """Get all index names."""
        return [
            cls.OPENCONFIG_SCHEMA,
            cls.SUZIEQ_SCHEMA,
            cls.EPISODIC_MEMORY,
            cls.DOCUMENTS,
        ]


# ============================================
# Logging Configuration
# ============================================
class LoggingConfig:
    """Logging settings."""
    
    LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    
    # Format
    FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    
    # File logging
    LOG_FILE = DATA_DIR / "olav.log"
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT = 5


# ============================================
# Initialize
# ============================================
# Ensure all directories exist on import
Paths.ensure_directories()
