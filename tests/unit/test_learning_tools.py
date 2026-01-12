"""Unit tests for learning_tools.py module.

Tests LangChain tool wrappers for learning capabilities.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from olav.tools.learning_tools import (
    EmbedKnowledgeInput,
    EmbedKnowledgeTool,
    SuggestSolutionFilenameInput,
    SuggestSolutionFilenameTool,
    UpdateAliasesInput,
    UpdateAliasesTool,
    embed_knowledge_tool,
    suggest_filename_tool,
    update_aliases_tool,
)


@pytest.mark.unit
class TestUpdateAliasesTool:
    """Test UpdateAliasesTool LangChain wrapper."""

    def test_tool_metadata(self) -> None:
        """Test tool has correct metadata."""
        assert update_aliases_tool.name == "update_aliases"
        assert "alias" in update_aliases_tool.description.lower()
        assert update_aliases_tool.args_schema == UpdateAliasesInput

    def test_input_schema_fields(self) -> None:
        """Test input schema has correct fields."""
        schema = UpdateAliasesInput.model_fields
        assert "alias" in schema
        assert "actual_value" in schema
        assert "alias_type" in schema
        assert "platform" in schema
        assert "notes" in schema

    def test_input_schema_defaults(self) -> None:
        """Test input schema has correct defaults."""
        schema = UpdateAliasesInput.model_fields
        assert schema["platform"].default == "unknown"
        assert schema["notes"].default == ""

    def test_run_success(self) -> None:
        """Test successful alias update."""
        with patch("olav.tools.learning_tools.update_aliases") as mock_update:
            mock_update.return_value = True

            result = update_aliases_tool._run(
                alias="核心路由器",
                actual_value="R1, R2",
                alias_type="device",
                platform="cisco_ios",
                notes="Core routers",
            )

            assert "✅" in result
            assert "核心路由器" in result
            assert "R1, R2" in result
            mock_update.assert_called_once()

    def test_run_failure(self) -> None:
        """Test failed alias update."""
        with patch("olav.tools.learning_tools.update_aliases") as mock_update:
            mock_update.return_value = False

            result = update_aliases_tool._run(
                alias="test", actual_value="value", alias_type="device"
            )

            assert "❌" in result
            assert "Failed" in result

    def test_run_exception_handling(self) -> None:
        """Test exception handling in tool."""
        with patch("olav.tools.learning_tools.update_aliases") as mock_update:
            mock_update.side_effect = Exception("Test error")

            result = update_aliases_tool._run(
                alias="test", actual_value="value", alias_type="device"
            )

            assert "❌" in result
            assert "Error updating alias" in result


@pytest.mark.unit
class TestSuggestSolutionFilenameTool:
    """Test SuggestSolutionFilenameTool LangChain wrapper."""

    def test_tool_metadata(self) -> None:
        """Test tool has correct metadata."""
        assert suggest_filename_tool.name == "suggest_solution_filename"
        assert "filename" in suggest_filename_tool.description.lower()
        assert suggest_filename_tool.args_schema == SuggestSolutionFilenameInput

    def test_input_schema_fields(self) -> None:
        """Test input schema has correct fields."""
        schema = SuggestSolutionFilenameInput.model_fields
        assert "problem_type" in schema
        assert "device" in schema
        assert "symptom" in schema

    def test_input_schema_defaults(self) -> None:
        """Test input schema has correct defaults."""
        schema = SuggestSolutionFilenameInput.model_fields
        assert schema["device"].default == ""
        assert schema["symptom"].default == ""

    def test_run_with_all_params(self) -> None:
        """Test with all parameters provided."""
        with patch("olav.tools.learning_tools.suggest_solution_filename") as mock_suggest:
            mock_suggest.return_value = "crc-r1-optical-power"

            result = suggest_filename_tool._run(
                problem_type="CRC", device="R1", symptom="optical power"
            )

            assert "Suggested filename:" in result
            assert "crc-r1-optical-power.md" in result
            mock_suggest.assert_called_once_with(
                problem_type="CRC", device="R1", symptom="optical power"
            )

    def test_run_with_minimal_params(self) -> None:
        """Test with minimal parameters."""
        with patch("olav.tools.learning_tools.suggest_solution_filename") as mock_suggest:
            mock_suggest.return_value = "bgp"

            result = suggest_filename_tool._run(problem_type="BGP")

            assert "Suggested filename:" in result
            assert "bgp.md" in result


@pytest.mark.unit
class TestEmbedKnowledgeTool:
    """Test EmbedKnowledgeTool LangChain wrapper."""

    def test_tool_metadata(self) -> None:
        """Test tool has correct metadata."""
        assert embed_knowledge_tool.name == "embed_knowledge"
        assert "embed" in embed_knowledge_tool.description.lower()
        assert embed_knowledge_tool.args_schema == EmbedKnowledgeInput

    def test_input_schema_fields(self) -> None:
        """Test input schema has correct fields."""
        schema = EmbedKnowledgeInput.model_fields
        assert "file_path" in schema
        assert "source_type" in schema
        assert "platform" in schema

    def test_input_schema_defaults(self) -> None:
        """Test input schema has correct defaults."""
        schema = EmbedKnowledgeInput.model_fields
        assert schema["source_type"].default == "report"
        assert schema["platform"].default is None

    def test_run_file_not_found(self) -> None:
        """Test with non-existent file."""
        result = embed_knowledge_tool._run(file_path="/nonexistent/file.md")

        assert "❌" in result
        assert "not found" in result

    def test_run_unsupported_file_type(self) -> None:
        """Test with unsupported file type (real file)."""
        with patch("olav.tools.learning_tools.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.is_file.return_value = True
            type(mock_path).suffix = PropertyMock(return_value=".txt")
            mock_path.is_absolute.return_value = False
            mock_path_cls.return_value = mock_path

            result = embed_knowledge_tool._run(file_path="test.txt")

            assert "❌" in result
            assert "Only markdown files" in result

    def test_run_exception_handling(self) -> None:
        """Test exception handling in tool."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_embedder_cls.side_effect = Exception("Embedding error")

            result = embed_knowledge_tool._run(file_path="test.md")

            assert "❌" in result
            assert "Error embedding knowledge" in result

    def _setup_file_path_mock(self):
        """Helper to set up a standard file path mock."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        type(mock_path).suffix = PropertyMock(return_value=".md")
        mock_path.name = "test.md"
        mock_path.is_absolute.return_value = True
        return mock_path

    def test_source_type_mapping_report(self) -> None:
        """Test source_type 'report' maps to source_id 3."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_file_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_file.return_value = 1
                mock_embedder_cls.return_value = mock_embedder

                embed_knowledge_tool._run(file_path="test.md", source_type="report")

                mock_embedder.embed_file.assert_called_once()
                call_kwargs = mock_embedder.embed_file.call_args[1]
                assert call_kwargs["source_id"] == 3

    def test_source_type_mapping_skill(self) -> None:
        """Test source_type 'skill' maps to source_id 1."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_file_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_file.return_value = 1
                mock_embedder_cls.return_value = mock_embedder

                embed_knowledge_tool._run(file_path="test.md", source_type="skill")

                call_kwargs = mock_embedder.embed_file.call_args[1]
                assert call_kwargs["source_id"] == 1

    def test_source_type_mapping_knowledge(self) -> None:
        """Test source_type 'knowledge' maps to source_id 2."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_file_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_file.return_value = 1
                mock_embedder_cls.return_value = mock_embedder

                embed_knowledge_tool._run(file_path="test.md", source_type="knowledge")

                call_kwargs = mock_embedder.embed_file.call_args[1]
                assert call_kwargs["source_id"] == 2

    def test_source_type_mapping_unknown(self) -> None:
        """Test unknown source_type defaults to source_id 3."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_file_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_file.return_value = 1
                mock_embedder_cls.return_value = mock_embedder

                embed_knowledge_tool._run(file_path="test.md", source_type="unknown")

                call_kwargs = mock_embedder.embed_file.call_args[1]
                assert call_kwargs["source_id"] == 3

    def test_run_file_success(self) -> None:
        """Test successful file embedding."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_file_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_file.return_value = 5
                mock_embedder_cls.return_value = mock_embedder

                result = embed_knowledge_tool._run(file_path="test.md", source_type="report")

                assert "✅" in result
                assert "5 chunks indexed" in result

    def test_run_file_already_indexed(self) -> None:
        """Test file already indexed (returns 0)."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_file_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_file.return_value = 0
                mock_embedder_cls.return_value = mock_embedder

                result = embed_knowledge_tool._run(file_path="test.md")

                assert "⚠️" in result
                assert "already indexed" in result

    def _setup_dir_path_mock(self):
        """Helper to set up a directory path mock."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = False
        mock_path.is_dir.return_value = True
        mock_path.name = "skills"
        mock_path.is_absolute.return_value = True
        return mock_path

    def test_run_directory_success(self) -> None:
        """Test successful directory embedding."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_dir_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_directory.return_value = {
                    "indexed": 10,
                    "skipped": 2,
                }
                mock_embedder_cls.return_value = mock_embedder

                result = embed_knowledge_tool._run(
                    file_path="skills/", source_type="skill"
                )

                assert "✅" in result
                assert "10 chunks indexed" in result
                assert "2 skipped" in result

    def test_run_directory_no_files(self) -> None:
        """Test directory with no new files."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_dir_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_directory.return_value = {"indexed": 0, "skipped": 0}
                mock_embedder_cls.return_value = mock_embedder

                result = embed_knowledge_tool._run(file_path="empty/")

                assert "⚠️" in result
                assert "No new files" in result

    def test_platform_parameter_passed(self) -> None:
        """Test platform parameter is passed to embedder."""
        with patch("olav.tools.learning_tools.KnowledgeEmbedder") as mock_embedder_cls:
            mock_path = self._setup_file_path_mock()

            with patch("olav.tools.learning_tools.Path", return_value=mock_path):
                mock_embedder = MagicMock()
                mock_embedder.embed_file.return_value = 1
                mock_embedder_cls.return_value = mock_embedder

                embed_knowledge_tool._run(file_path="test.md", platform="cisco_ios")

                call_kwargs = mock_embedder.embed_file.call_args[1]
                assert call_kwargs["platform"] == "cisco_ios"


@pytest.mark.unit
class TestLearningToolsExports:
    """Test module exports."""

    def test_module_exports_all_tools(self) -> None:
        """Test all tools are exported in __all__."""
        from olav.tools import learning_tools

        expected = {"update_aliases_tool", "suggest_filename_tool", "embed_knowledge_tool"}

        assert set(learning_tools.__all__) == expected
