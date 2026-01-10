"""LLM Factory for creating chat and embedding models.

Uses LangChain's init_chat_model() for unified provider support including
OpenAI, Azure, and Ollama.
"""

import logging
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_openai import OpenAIEmbeddings

from config.settings import settings

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM instances using init_chat_model()."""

    @staticmethod
    def get_chat_model(
        json_mode: bool = False,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create a chat model instance using LangChain init_chat_model.

        Args:
            json_mode: Whether to enable JSON output mode
            temperature: Override default temperature
            **kwargs: Additional model parameters

        Returns:
            Configured chat model instance
        """
        temp = temperature if temperature is not None else settings.llm_temperature
        provider = settings.llm_provider
        model_name = settings.llm_model_name

        # Build configuration based on provider
        config: dict[str, Any] = {
            "temperature": temp,
            "max_tokens": settings.llm_max_tokens,
        }

        if provider == "ollama":
            config["base_url"] = settings.llm_base_url or "http://localhost:11434"
            if json_mode:
                config["format"] = "json"
            logger.debug(
                f"Creating Ollama chat model: model={model_name}, base_url={config['base_url']}"
            )
        elif provider == "openai":
            config["api_key"] = settings.llm_api_key
            if settings.llm_base_url:
                config["base_url"] = settings.llm_base_url
            if json_mode:
                config["model_kwargs"] = {"response_format": {"type": "json_object"}}
            logger.debug(f"Creating OpenAI chat model: {model_name}")
        elif provider == "azure":
            config["api_key"] = settings.llm_api_key
            logger.debug(f"Creating Azure chat model: {model_name}")

        return init_chat_model(model_name, model_provider=provider, **config, **kwargs)

    @staticmethod
    def get_embedding_model() -> OpenAIEmbeddings:
        """Create an embedding model instance.

        Returns:
            Configured embedding model instance
        """
        provider = settings.embedding_provider
        api_key = settings.embedding_api_key or settings.llm_api_key
        model = settings.embedding_model

        if provider == "openai":
            if not api_key:
                logger.warning("No embedding API key set")
            return OpenAIEmbeddings(
                model=model,
                api_key=api_key,
            )

        if provider == "ollama":
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError as e:
                msg = "langchain-ollama not installed"
                raise ImportError(msg) from e

            base_url = settings.embedding_base_url or "http://localhost:11434"
            return OllamaEmbeddings(model=model, base_url=base_url)

        msg = f"Unsupported embedding provider: {provider}"
        raise ValueError(msg)
