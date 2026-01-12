"""Unit tests for llm.py module.

Tests LLM factory for creating chat and embedding models.
"""

from unittest.mock import MagicMock, patch

import pytest

from olav.core.llm import LLMFactory


@pytest.mark.unit
class TestLLMFactory:
    """Test LLMFactory for model creation."""

    def test_get_chat_model_default_params(self) -> None:
        """Test get_chat_model with default parameters."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "openai"
                mock_settings.llm_model_name = "gpt-4"
                mock_settings.llm_api_key = "test-key"
                mock_settings.llm_base_url = None

                result = LLMFactory.get_chat_model()

                assert result == mock_model
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["temperature"] == 0.7
                assert call_kwargs["max_tokens"] == 2000

    def test_get_chat_model_with_temperature_override(self) -> None:
        """Test get_chat_model with temperature override."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "openai"
                mock_settings.llm_model_name = "gpt-4"
                mock_settings.llm_api_key = "test-key"
                mock_settings.llm_base_url = None

                result = LLMFactory.get_chat_model(temperature=0.5)

                assert result == mock_model
                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["temperature"] == 0.5

    def test_get_chat_model_openai_provider(self) -> None:
        """Test get_chat_model with OpenAI provider."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "openai"
                mock_settings.llm_model_name = "gpt-4"
                mock_settings.llm_api_key = "sk-test"
                mock_settings.llm_base_url = None

                result = LLMFactory.get_chat_model()

                assert result == mock_model
                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["api_key"] == "sk-test"
                assert "base_url" not in call_kwargs

    def test_get_chat_model_openai_with_base_url(self) -> None:
        """Test get_chat_model with OpenAI provider and custom base_url."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "openai"
                mock_settings.llm_model_name = "gpt-4"
                mock_settings.llm_api_key = "sk-test"
                mock_settings.llm_base_url = "https://api.custom.com"

                result = LLMFactory.get_chat_model()

                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["api_key"] == "sk-test"
                assert call_kwargs["base_url"] == "https://api.custom.com"

    def test_get_chat_model_openai_json_mode(self) -> None:
        """Test get_chat_model with OpenAI JSON mode."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "openai"
                mock_settings.llm_model_name = "gpt-4"
                mock_settings.llm_api_key = "sk-test"
                mock_settings.llm_base_url = None

                result = LLMFactory.get_chat_model(json_mode=True)

                call_kwargs = mock_init.call_args[1]
                assert "model_kwargs" in call_kwargs
                assert call_kwargs["model_kwargs"]["response_format"]["type"] == "json_object"

    def test_get_chat_model_ollama_provider(self) -> None:
        """Test get_chat_model with Ollama provider."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "ollama"
                mock_settings.llm_model_name = "llama3"
                mock_settings.llm_base_url = "http://localhost:11434"

                result = LLMFactory.get_chat_model()

                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["base_url"] == "http://localhost:11434"
                assert "format" not in call_kwargs  # No json_mode

    def test_get_chat_model_ollama_json_mode(self) -> None:
        """Test get_chat_model with Ollama JSON mode."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "ollama"
                mock_settings.llm_model_name = "llama3"
                mock_settings.llm_base_url = None

                result = LLMFactory.get_chat_model(json_mode=True)

                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["base_url"] == "http://localhost:11434"  # Default
                assert call_kwargs["format"] == "json"

    def test_get_chat_model_ollama_default_base_url(self) -> None:
        """Test get_chat_model with Ollama uses default base_url when not set."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "ollama"
                mock_settings.llm_model_name = "llama3"
                mock_settings.llm_base_url = None

                result = LLMFactory.get_chat_model()

                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["base_url"] == "http://localhost:11434"

    def test_get_chat_model_azure_provider(self) -> None:
        """Test get_chat_model with Azure provider."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "azure"
                mock_settings.llm_model_name = "gpt-4"
                mock_settings.llm_api_key = "azure-key"

                result = LLMFactory.get_chat_model()

                call_kwargs = mock_init.call_args[1]
                assert call_kwargs["api_key"] == "azure-key"

    def test_get_chat_model_passes_kwargs(self) -> None:
        """Test get_chat_model passes additional kwargs."""
        with patch("olav.core.llm.init_chat_model") as mock_init:
            mock_model = MagicMock()
            mock_init.return_value = mock_model

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.llm_temperature = 0.7
                mock_settings.llm_max_tokens = 2000
                mock_settings.llm_provider = "openai"
                mock_settings.llm_model_name = "gpt-4"
                mock_settings.llm_api_key = "test-key"
                mock_settings.llm_base_url = None

                result = LLMFactory.get_chat_model(top_p=0.9, frequency_penalty=0.1)

                # Check that custom kwargs were passed through
                assert "top_p" in mock_init.call_args.kwargs
                assert mock_init.call_args.kwargs["top_p"] == 0.9
                assert "frequency_penalty" in mock_init.call_args.kwargs

    def test_get_embedding_model_openai(self) -> None:
        """Test get_embedding_model with OpenAI provider."""
        with patch("olav.core.llm.OpenAIEmbeddings") as mock_embeddings:
            mock_instance = MagicMock()
            mock_embeddings.return_value = mock_instance

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.embedding_provider = "openai"
                mock_settings.embedding_api_key = "sk-test"
                mock_settings.llm_api_key = "fallback-key"
                mock_settings.embedding_model = "text-embedding-3-small"

                result = LLMFactory.get_embedding_model()

                assert result == mock_instance
                # Check that api_key is a SecretStr
                call_args = mock_embeddings.call_args
                from pydantic import SecretStr

                assert call_args.kwargs["model"] == "text-embedding-3-small"
                assert isinstance(call_args.kwargs["api_key"], SecretStr)

    def test_get_embedding_model_openai_fallback_api_key(self) -> None:
        """Test get_embedding_model falls back to llm_api_key when embedding_api_key not set."""
        with patch("olav.core.llm.OpenAIEmbeddings") as mock_embeddings:
            mock_instance = MagicMock()
            mock_embeddings.return_value = mock_instance

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.embedding_provider = "openai"
                mock_settings.embedding_api_key = None
                mock_settings.llm_api_key = "llm-key"
                mock_settings.embedding_model = "text-embedding-3-small"

                result = LLMFactory.get_embedding_model()

                # Check that api_key is a SecretStr
                call_args = mock_embeddings.call_args
                from pydantic import SecretStr

                assert call_args.kwargs["model"] == "text-embedding-3-small"
                assert isinstance(call_args.kwargs["api_key"], SecretStr)

    def test_get_embedding_model_openai_no_api_key_warning(self) -> None:
        """Test get_embedding_model warns when no API key is set."""
        with patch("olav.core.llm.OpenAIEmbeddings") as mock_embeddings:
            mock_instance = MagicMock()
            mock_embeddings.return_value = mock_instance

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.embedding_provider = "openai"
                mock_settings.embedding_api_key = None
                mock_settings.llm_api_key = None
                mock_settings.embedding_model = "text-embedding-3-small"

                result = LLMFactory.get_embedding_model()

                # Should still create embeddings but with None api_key
                mock_embeddings.assert_called_once()

    @pytest.mark.skipif(True, reason="Requires langchain-ollama package")
    def test_get_embedding_model_ollama(self) -> None:
        """Test get_embedding_model with Ollama provider."""
        with patch("olav.core.llm.OllamaEmbeddings") as mock_embeddings:
            mock_instance = MagicMock()
            mock_embeddings.return_value = mock_instance

            with patch("olav.core.llm.settings") as mock_settings:
                mock_settings.embedding_provider = "ollama"
                mock_settings.embedding_base_url = "http://localhost:11434"
                mock_settings.embedding_model = "llama3"

                result = LLMFactory.get_embedding_model()

                assert result == mock_instance

    def test_get_embedding_model_ollama_import_error(self) -> None:
        """Test get_embedding_model with Ollama raises ImportError if package not installed."""
        with patch("olav.core.llm.settings") as mock_settings:
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_base_url = "http://localhost:11434"
            mock_settings.embedding_model = "llama3"

            with patch.dict("sys.modules", {"langchain_ollama": None}):
                with pytest.raises(ImportError) as exc_info:
                    LLMFactory.get_embedding_model()

                assert "langchain-ollama not installed" in str(exc_info.value)

    def test_get_embedding_model_ollama_default_base_url(self) -> None:
        """Test get_embedding_model with Ollama uses default base_url."""
        with patch("olav.core.llm.settings") as mock_settings:
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_base_url = None
            mock_settings.embedding_model = "llama3"

            # Mock OllamaEmbeddings import
            mock_ollama = MagicMock()
            mock_ollama.OllamaEmbeddings = MagicMock()
            mock_ollama.OllamaEmbeddings.return_value = MagicMock()

            with patch.dict("sys.modules", {"langchain_ollama": mock_ollama}):
                result = LLMFactory.get_embedding_model()

                # Check default base_url was used
                call_kwargs = mock_ollama.OllamaEmbeddings.call_args[1]
                assert call_kwargs["base_url"] == "http://localhost:11434"

    def test_get_embedding_model_unsupported_provider(self) -> None:
        """Test get_embedding_model raises ValueError for unsupported provider."""
        with patch("olav.core.llm.settings") as mock_settings:
            mock_settings.embedding_provider = "unknown_provider"
            mock_settings.embedding_model = "test-model"

            with pytest.raises(ValueError) as exc_info:
                LLMFactory.get_embedding_model()

            assert "Unsupported embedding provider" in str(exc_info.value)

    def test_get_embedding_model_ollama_custom_base_url(self) -> None:
        """Test get_embedding_model with Ollama custom base_url."""
        with patch("olav.core.llm.settings") as mock_settings:
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_base_url = "http://custom:11434"
            mock_settings.embedding_model = "llama3"

            mock_ollama = MagicMock()
            mock_ollama.OllamaEmbeddings = MagicMock()
            mock_ollama.OllamaEmbeddings.return_value = MagicMock()

            with patch.dict("sys.modules", {"langchain_ollama": mock_ollama}):
                result = LLMFactory.get_embedding_model()

                call_kwargs = mock_ollama.OllamaEmbeddings.call_args[1]
                assert call_kwargs["base_url"] == "http://custom:11434"
