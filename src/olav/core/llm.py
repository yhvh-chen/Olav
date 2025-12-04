"""LLM Factory for creating chat and embedding models.

Refactored to use LangChain 1.10's init_chat_model() for unified model initialization.
Supports 15+ providers with a single function call.

LangChain 1.10 Middleware Integration:
- ModelRetryMiddleware: Automatic retry with exponential backoff
- ModelFallbackMiddleware: Automatic failover to backup models

LangSmith Integration:
- Optional tracing for debugging and performance analysis
- Enable via LANGSMITH_ENABLED=true and LANGSMITH_API_KEY in .env
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from langchain.agents.middleware import ModelFallbackMiddleware, ModelRetryMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_openai import OpenAIEmbeddings

# Add config to path if not already there
config_path = Path(__file__).parent.parent.parent.parent / "config"
if str(config_path) not in sys.path:
    sys.path.insert(0, str(config_path.parent))

from config.settings import LLMConfig, LLMRetryConfig

from olav.core.settings import settings as env_settings

logger = logging.getLogger(__name__)


# ============================================
# LangSmith Configuration
# ============================================
def configure_langsmith() -> bool:
    """Configure LangSmith tracing if enabled.
    
    Sets environment variables required by LangChain to enable tracing.
    Call this once at startup before creating any LLM instances.
    
    Returns:
        True if LangSmith was enabled, False otherwise
    """
    if not env_settings.langsmith_enabled:
        return False
    
    if not env_settings.langsmith_api_key:
        logger.warning("LangSmith enabled but LANGSMITH_API_KEY not set")
        return False
    
    # Set LangChain environment variables
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = env_settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = env_settings.langsmith_project
    os.environ["LANGCHAIN_ENDPOINT"] = env_settings.langsmith_endpoint
    
    logger.info(
        f"LangSmith tracing enabled: project={env_settings.langsmith_project}, "
        f"endpoint={env_settings.langsmith_endpoint}"
    )
    return True


def is_langsmith_enabled() -> bool:
    """Check if LangSmith tracing is currently enabled."""
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"


# ============================================
# Retry Configuration (from config/settings.py)
# ============================================
# Exceptions that should trigger retry (transient errors)
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    TimeoutError,
    ConnectionError,
)

# Try to add provider-specific exceptions
try:
    from openai import APITimeoutError, RateLimitError

    RETRYABLE_EXCEPTIONS = (*RETRYABLE_EXCEPTIONS, APITimeoutError, RateLimitError)
except ImportError:
    pass  # openai package not installed


class LLMFactory:
    """Factory for creating LLM instances using init_chat_model().

    LangChain 1.10 provides init_chat_model() which supports 15+ providers
    (openai, anthropic, azure_openai, ollama, etc.) with a unified interface.

    Middleware Support:
    - get_chat_model(): Basic model without middleware
    - get_retry_middleware(): ModelRetryMiddleware for transient errors
    - get_fallback_middleware(): ModelFallbackMiddleware for model failover
    """

    # Cached middleware instances (singleton pattern)
    _retry_middleware: ModelRetryMiddleware | None = None
    _fallback_middleware: ModelFallbackMiddleware | None = None

    @staticmethod
    def get_chat_model(
        json_mode: bool = False,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create a chat model instance using init_chat_model().

        Args:
            json_mode: Whether to enable JSON output mode
            temperature: Override default temperature
            **kwargs: Additional model parameters

        Returns:
            Configured chat model instance
        """
        temp = temperature if temperature is not None else LLMConfig.TEMPERATURE

        # Build configurable fields for init_chat_model
        config: dict[str, Any] = {
            "temperature": temp,
            "max_tokens": LLMConfig.MAX_TOKENS,
        }

        # Provider-specific configuration
        provider = env_settings.llm_provider
        model_name = env_settings.llm_model_name or LLMConfig.MODEL_NAME

        if provider == "openai":
            config["api_key"] = env_settings.llm_api_key
            if LLMConfig.BASE_URL:
                config["base_url"] = LLMConfig.BASE_URL
            # Sequential tool execution for OpenRouter compatibility
            config["model_kwargs"] = {"parallel_tool_calls": False}
            if json_mode:
                config["model_kwargs"]["response_format"] = {"type": "json_object"}
        elif provider == "ollama":
            if json_mode:
                config["format"] = "json"
        elif provider == "azure_openai":
            config["api_key"] = env_settings.llm_api_key

        logger.debug(f"Initializing chat model: provider={provider}, model={model_name}")
        return init_chat_model(model_name, model_provider=provider, **config, **kwargs)

    @staticmethod
    def get_embedding_model() -> OpenAIEmbeddings:
        """Create an embedding model instance.

        Uses separate embedding configuration because OpenRouter doesn't support embeddings.
        Falls back to OpenAI direct API or local Ollama.

        Returns:
            Configured embedding model instance

        Raises:
            ValueError: If provider is not supported
        """
        # Use dedicated embedding settings (not LLM settings)
        provider = env_settings.embedding_provider
        api_key = env_settings.embedding_api_key or env_settings.llm_api_key
        base_url = env_settings.embedding_base_url
        model = env_settings.embedding_model
        
        if provider == "openai":
            if not api_key:
                logger.warning("No EMBEDDING_API_KEY set. Embedding features may fail.")
            return OpenAIEmbeddings(
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
        if provider == "ollama":
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError as e:
                msg = "langchain-ollama not installed. Run: uv add langchain-ollama"
                raise ImportError(msg) from e

            # Use model from settings, strip :latest suffix if present for cleaner logging
            model_name = model.replace(":latest", "") if model else "nomic-embed-text"
            ollama_url = base_url or "http://127.0.0.1:11434"
            logger.info(f"Using Ollama embedding model: {model_name} at {ollama_url}")
            return OllamaEmbeddings(model=model_name, base_url=ollama_url)
        
        msg = f"Unsupported embedding provider: {provider}"
        raise ValueError(msg)

    @staticmethod
    def get_vision_model():
        """Create a vision-capable model instance.

        Used for analyzing network diagrams, topology screenshots, etc.

        Returns:
            Configured vision model instance (ChatOpenAI with vision support)
        """
        from langchain_openai import ChatOpenAI
        
        provider = env_settings.vision_provider
        api_key = env_settings.vision_api_key or env_settings.llm_api_key
        base_url = env_settings.vision_base_url
        model = env_settings.vision_model
        
        if provider == "openai":
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                max_tokens=4096,
            )
        if provider == "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError as e:
                msg = "langchain-ollama not installed. Run: uv add langchain-ollama"
                raise ImportError(msg) from e

            return ChatOllama(model="llava")  # LLaVA for local vision
        
        msg = f"Unsupported vision provider: {provider}"
        raise ValueError(msg)

    # ============================================
    # LangChain 1.10 Middleware Factory Methods
    # ============================================

    @classmethod
    def get_retry_middleware(
        cls,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
        initial_delay: float | None = None,
        max_delay: float | None = None,
        jitter: bool | None = None,
    ) -> ModelRetryMiddleware:
        """Get ModelRetryMiddleware for automatic retry with exponential backoff.

        Handles transient errors like rate limits, timeouts, and connection errors.
        Uses singleton pattern to avoid creating multiple instances.
        Default values are loaded from config/settings.py LLMRetryConfig.

        Args:
            max_retries: Maximum retry attempts (default: LLMRetryConfig.MAX_RETRIES)
            backoff_factor: Multiplier for exponential backoff (default: LLMRetryConfig.BACKOFF_FACTOR)
            initial_delay: Initial delay in seconds (default: LLMRetryConfig.INITIAL_DELAY)
            max_delay: Maximum delay cap in seconds (default: LLMRetryConfig.MAX_DELAY)
            jitter: Add randomness to prevent thundering herd (default: LLMRetryConfig.JITTER)

        Returns:
            Configured ModelRetryMiddleware instance

        Example:
            >>> retry = LLMFactory.get_retry_middleware(max_retries=5)
            >>> agent = create_agent(model=model, middleware=[retry])
        """
        if cls._retry_middleware is None:
            # Use config defaults if not specified
            _max_retries = max_retries if max_retries is not None else LLMRetryConfig.MAX_RETRIES
            _backoff_factor = backoff_factor if backoff_factor is not None else LLMRetryConfig.BACKOFF_FACTOR
            _initial_delay = initial_delay if initial_delay is not None else LLMRetryConfig.INITIAL_DELAY
            _max_delay = max_delay if max_delay is not None else LLMRetryConfig.MAX_DELAY
            _jitter = jitter if jitter is not None else LLMRetryConfig.JITTER
            
            cls._retry_middleware = ModelRetryMiddleware(
                max_retries=_max_retries,
                retry_on=RETRYABLE_EXCEPTIONS,
                backoff_factor=_backoff_factor,
                initial_delay=_initial_delay,
                max_delay=_max_delay,
                jitter=_jitter,
                on_failure="continue",  # Return error message instead of raising
            )
            logger.info(
                f"Created ModelRetryMiddleware: max_retries={_max_retries}, "
                f"retry_on={[e.__name__ for e in RETRYABLE_EXCEPTIONS]}"
            )
        return cls._retry_middleware

    @classmethod
    def get_fallback_middleware(
        cls,
        fallback_models: list[str] | None = None,
    ) -> ModelFallbackMiddleware:
        """Get ModelFallbackMiddleware for automatic model failover.

        When primary model fails completely (not transient), automatically
        switches to backup models in order.

        Args:
            fallback_models: Ordered list of fallback model strings.
                Format: "provider:model_name" (e.g., "openai:gpt-4o-mini")
                If None, uses default fallback chain from config.

        Returns:
            Configured ModelFallbackMiddleware instance

        Example:
            >>> fallback = LLMFactory.get_fallback_middleware(
            ...     ["openai:gpt-4o-mini", "ollama:llama3"]
            ... )
            >>> agent = create_agent(model=model, middleware=[fallback])
        """
        if cls._fallback_middleware is None:
            # Default fallback chain if not specified
            if fallback_models is None:
                fallback_models = _get_default_fallback_models()

            if not fallback_models:
                # No fallbacks configured - create with primary model as fallback
                primary = f"{env_settings.llm_provider}:{env_settings.llm_model_name}"
                logger.warning(
                    f"No fallback models configured, using primary model only: {primary}"
                )
                cls._fallback_middleware = ModelFallbackMiddleware(primary)
            else:
                cls._fallback_middleware = ModelFallbackMiddleware(
                    fallback_models[0],
                    *fallback_models[1:],
                )
                logger.info(f"Created ModelFallbackMiddleware: models={fallback_models}")

        return cls._fallback_middleware

    @classmethod
    def get_middleware_stack(cls) -> list:
        """Get the standard middleware stack for resilient LLM calls.

        Returns both retry and fallback middleware in the correct order.
        Retry is applied first (inner), then fallback (outer).

        Returns:
            List of middleware instances [retry, fallback]

        Example:
            >>> middleware = LLMFactory.get_middleware_stack()
            >>> agent = create_agent(model=model, middleware=middleware)
        """
        return [
            cls.get_retry_middleware(),
            cls.get_fallback_middleware(),
        ]

    @classmethod
    def reset_middleware(cls) -> None:
        """Reset cached middleware instances.

        Useful for testing or reconfiguration.
        """
        cls._retry_middleware = None
        cls._fallback_middleware = None
        logger.debug("Reset LLM middleware cache")


def _get_default_fallback_models() -> list[str]:
    """Get default fallback model chain from config or environment.

    Priority:
    1. LLMConfig.FALLBACK_MODELS if defined
    2. Environment variable LLM_FALLBACK_MODELS (comma-separated)
    3. Empty list (no fallbacks)

    Returns:
        List of model strings in fallback order
    """
    # Try config first
    if hasattr(LLMConfig, "FALLBACK_MODELS") and LLMConfig.FALLBACK_MODELS:
        return LLMConfig.FALLBACK_MODELS

    # Try environment variable
    import os

    fallback_env = os.getenv("LLM_FALLBACK_MODELS", "")
    if fallback_env:
        return [m.strip() for m in fallback_env.split(",") if m.strip()]

    # Default: use a smaller/cheaper model as fallback
    provider = env_settings.llm_provider
    if provider == "openai":
        return ["openai:gpt-4o-mini"]
    if provider == "ollama":
        return ["ollama:llama3.2"]

    return []
