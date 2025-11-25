"""LLM Factory for creating chat and embedding models."""

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Add config to path if not already there
config_path = Path(__file__).parent.parent.parent.parent / "config"
if str(config_path) not in sys.path:
    sys.path.insert(0, str(config_path.parent))

from config.settings import LLMConfig
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_openai.chat_models.base import _convert_dict_to_message

from olav.core.settings import settings as env_settings

logger = logging.getLogger(__name__)


def _fixed_convert_dict_to_message(message_dict: dict) -> Any:
    """Fixed version of _convert_dict_to_message that handles JSON string arguments.

    OpenRouter/DeepSeek returns tool_calls with arguments as JSON strings.

    CRITICAL INSIGHT: We CANNOT pre-parse arguments from str to dict, because
    parse_tool_call() will call json.loads() on it, causing TypeError.

    Strategy: Let parse_tool_call handle JSON parsing. Only fix invalid_tool_calls.
    """
    # DO NOT modify tool_calls - let parse_tool_call handle it
    # (Previous code pre-parsed arguments, which broke parse_tool_call's json.loads)

    # Fix invalid_tool_calls: args from dict → str (if needed)
    invalid_tool_calls = message_dict.get("invalid_tool_calls")
    if invalid_tool_calls:  # Check if not None and not empty
        logger.debug(f"Found {len(invalid_tool_calls)} invalid_tool_calls: {invalid_tool_calls}")
        for i, tool_call in enumerate(invalid_tool_calls):
            if "args" in tool_call:
                args = tool_call["args"]
                # InvalidToolCall.args MUST be str, convert dict back to str
                if isinstance(args, dict):
                    try:
                        tool_call["args"] = json.dumps(args)
                        logger.debug(f"Serialized invalid_tool_call[{i}] args to JSON string")
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Failed to serialize invalid_tool_call[{i}] args: {e}")
                        tool_call["args"] = ""
                elif not isinstance(args, str):
                    logger.warning(
                        f"invalid_tool_call[{i}] args has unexpected type {type(args)}, converting to empty str"
                    )
                    tool_call["args"] = ""

    # Call original converter
    return _convert_dict_to_message(message_dict)


class FixedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with fixed tool call parsing for OpenRouter/DeepSeek.

    This class patches the message converter to handle JSON string arguments.
    """

    def _create_chat_result(self, response: Any, *args, **kwargs) -> Any:
        """Override to use fixed message converter."""
        # Temporarily patch the converter
        import langchain_openai.chat_models.base as base_module

        original_converter = base_module._convert_dict_to_message

        try:
            # Use our fixed converter
            base_module._convert_dict_to_message = _fixed_convert_dict_to_message
            return super()._create_chat_result(response, *args, **kwargs)
        finally:
            # Restore original converter
            base_module._convert_dict_to_message = original_converter


class LLMFactory:
    """Factory for creating LLM instances based on configured provider."""

    # One-time environment mapping flag
    _openai_env_mapped = False

    @classmethod
    def _ensure_openai_env(cls) -> None:
        """Map LLM_API_KEY to OPENAI_API_KEY if provider==openai and env not set.

        Avoid mapping if key is an OpenRouter style (sk-or-) because OpenAI SDK
        will reject it anyway; leave direct api_key usage in that scenario.
        """
        if cls._openai_env_mapped:
            return
        if env_settings.llm_provider == "openai":
            import os

            if (
                not os.getenv("OPENAI_API_KEY")
                and env_settings.llm_api_key
                and not env_settings.llm_api_key.startswith("sk-or-")
            ):
                os.environ["OPENAI_API_KEY"] = env_settings.llm_api_key
                logger.info("Mapped LLM_API_KEY to OPENAI_API_KEY for OpenAI provider")
        cls._openai_env_mapped = True

    @staticmethod
    def get_chat_model(
        json_mode: bool = False,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> ChatOpenAI:
        """Create a chat model instance.

        Args:
            json_mode: Whether to enable JSON output mode
            temperature: Override default temperature
            **kwargs: Additional model parameters

        Returns:
            Configured chat model instance

        Raises:
            ValueError: If provider is not supported
        """
        temp = temperature if temperature is not None else LLMConfig.TEMPERATURE

        if env_settings.llm_provider == "openai":
            # Ensure environment variable mapping (non-OpenRouter keys only)
            LLMFactory._ensure_openai_env()
            model_kwargs = {}

            if json_mode:
                model_kwargs["response_format"] = {"type": "json_object"}

            # DeepSeek via OpenRouter compatibility fixes:
            # 1. Use FixedChatOpenAI to handle JSON string arguments
            # 2. model_kwargs["parallel_tool_calls"]=False: Sequential execution (avoid warning)
            model_kwargs["parallel_tool_calls"] = False  # Sequential tool execution

            return FixedChatOpenAI(
                model=env_settings.llm_model_name or LLMConfig.MODEL_NAME,
                temperature=temp,
                max_tokens=LLMConfig.MAX_TOKENS,
                api_key=env_settings.llm_api_key,
                base_url=LLMConfig.BASE_URL,
                model_kwargs=model_kwargs,
                **kwargs,
            )
        if env_settings.llm_provider == "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError as e:
                msg = "langchain-ollama not installed. Run: uv add langchain-ollama"
                raise ImportError(msg) from e

            return ChatOllama(
                model=env_settings.llm_model_name or LLMConfig.MODEL_NAME,
                temperature=temp,
                format="json" if json_mode else None,
                **kwargs,
            )
        if env_settings.llm_provider == "azure":
            try:
                from langchain_openai import AzureChatOpenAI
            except ImportError as e:
                msg = "Azure OpenAI support requires langchain-openai"
                raise ImportError(msg) from e

            return AzureChatOpenAI(
                model=env_settings.llm_model_name or LLMConfig.MODEL_NAME,
                temperature=temp,
                api_key=env_settings.llm_api_key,
                **kwargs,
            )
        msg = f"Unsupported LLM provider: {env_settings.llm_provider}"
        raise ValueError(msg)

    @staticmethod
    def get_embedding_model() -> OpenAIEmbeddings:
        """Create an embedding model instance.

        Returns:
            Configured embedding model instance

        Raises:
            ValueError: If provider is not supported
        """
        if env_settings.llm_provider == "openai":
            LLMFactory._ensure_openai_env()
            return OpenAIEmbeddings(
                model=LLMConfig.EMBEDDING_MODEL,
                api_key=env_settings.llm_api_key,
                base_url=LLMConfig.BASE_URL,
            )
        if env_settings.llm_provider == "ollama":
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError as e:
                msg = "langchain-ollama not installed. Run: uv add langchain-ollama"
                raise ImportError(msg) from e

            return OllamaEmbeddings(model="nomic-embed-text")
        if env_settings.llm_provider == "azure":
            return OpenAIEmbeddings(
                model=LLMConfig.EMBEDDING_MODEL,
                api_key=env_settings.llm_api_key,
            )
        msg = f"Unsupported embedding provider: {env_settings.llm_provider}"
        raise ValueError(msg)
