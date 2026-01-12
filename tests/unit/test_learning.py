"""Unit tests for learning.py module.

Tests agentic self-learning capabilities for OLAV.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from olav.core.learning import (
    get_learning_guidance,
    learn_from_interaction,
    save_solution,
    suggest_solution_filename,
    update_aliases,
)


@pytest.mark.unit
class TestSaveSolution:
    """Test save_solution function."""

    def test_save_solution_creates_directory(self) -> None:
        """Test save_solution creates the knowledge directory."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "solutions"

            result = save_solution(
                title="test-case",
                problem="Test problem",
                process=["Step 1", "Step 2"],
                root_cause="Test cause",
                solution="Test solution",
                commands=["show version"],
                tags=["#test"],
                knowledge_dir=knowledge_dir,
            )

            # Verify directory was created
            assert knowledge_dir.exists()
            assert knowledge_dir.is_dir()

    def test_save_solution_creates_file(self) -> None:
        """Test save_solution creates a markdown file."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "solutions"

            result = save_solution(
                title="test-case",
                problem="Test problem",
                process=["Step 1", "Step 2"],
                root_cause="Test cause",
                solution="Test solution",
                commands=["show version"],
                tags=["#test"],
                knowledge_dir=knowledge_dir,
            )

            # Verify file was created
            filepath = Path(result)
            assert filepath.exists()
            assert filepath.is_file()
            assert filepath.suffix == ".md"

    def test_save_solution_content_format(self) -> None:
        """Test save_solution creates correct markdown content."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "solutions"

            result = save_solution(
                title="Test Case",
                problem="Network down",
                process=["Check interface", "Check cables"],
                root_cause="Cable unplugged",
                solution="Plug in cable",
                commands=["show interfaces"],
                tags=["#network", "#cable"],
                knowledge_dir=knowledge_dir,
            )

            # Read the file content
            content = Path(result).read_text(encoding="utf-8")

            # Verify key sections exist
            assert "# 案例: Test Case" in content
            assert "## 问题描述" in content
            assert "Network down" in content
            assert "## 排查过程" in content
            assert "1. Check interface" in content
            assert "2. Check cables" in content
            assert "## 根因" in content
            assert "Cable unplugged" in content
            assert "## 解决方案" in content
            assert "Plug in cable" in content
            assert "## 关键命令" in content
            assert "- show interfaces" in content
            assert "## 标签" in content

    def test_save_solution_sanitizes_title(self) -> None:
        """Test save_solution sanitizes title for filename."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "solutions"

            result = save_solution(
                title="Test Case/With Spaces",
                problem="Test",
                process=["Step 1"],
                root_cause="Cause",
                solution="Solution",
                commands=["cmd"],
                tags=[],
                knowledge_dir=knowledge_dir,
            )

            # Verify filename is sanitized
            filepath = Path(result)
            assert " " not in filepath.name
            assert "/" not in filepath.name

    def test_save_solution_empty_tags(self) -> None:
        """Test save_solution with empty tags uses uncategorized."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "solutions"

            result = save_solution(
                title="test",
                problem="Test",
                process=["Step 1"],
                root_cause="Cause",
                solution="Solution",
                commands=["cmd"],
                tags=[],  # Empty tags
                knowledge_dir=knowledge_dir,
            )

            content = Path(result).read_text(encoding="utf-8")
            assert "#uncategorized" in content


@pytest.mark.unit
class TestUpdateAliases:
    """Test update_aliases function."""

    def test_update_aliases_existing_table(self) -> None:
        """Test update_aliases inserts into existing table."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_file = Path(tmpdir) / "aliases.md"
            aliases_file.write_text(
                """# Aliases

| 别名 | 实际值 | 类型 | 平台 | 备注 |
|---|---|---|---|---|
| old_alias | R1 | device | cisco_ios | Old entry |
""",
                encoding="utf-8",
            )

            result = update_aliases(
                alias="new_alias",
                actual_value="R2",
                alias_type="device",
                platform="cisco_ios",
                notes="New entry",
                aliases_file=aliases_file,
            )

            assert result is True

            # Check new entry was added
            content = aliases_file.read_text(encoding="utf-8")
            assert "new_alias" in content
            assert "R2" in content

    def test_update_aliases_no_table(self) -> None:
        """Test update_aliases appends when no table found."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_file = Path(tmpdir) / "aliases.md"
            aliases_file.write_text("# Aliases\n\nNo table here.", encoding="utf-8")

            result = update_aliases(
                alias="test_alias",
                actual_value="R1",
                alias_type="device",
                aliases_file=aliases_file,
            )

            assert result is True
            # Should append new entry
            content = aliases_file.read_text(encoding="utf-8")
            assert "test_alias" in content


@pytest.mark.unit
class TestLearnFromInteraction:
    """Test learn_from_interaction function."""

    def test_learn_from_interaction_success_case(self) -> None:
        """Test learn_from_interaction identifies successful troubleshooting."""
        with patch("config.settings") as mock_settings:
            mock_settings.agent_dir = "/test/agent"

            result = learn_from_interaction(
                query="网络故障，如何排查？",
                response="Let me help troubleshoot...",
                success=True,
            )

            assert "should_save_solution" in result
            assert result["should_save_solution"] is True

    def test_learn_from_interaction_no_keywords(self) -> None:
        """Test learn_from_interaction with no troubleshooting keywords."""
        with patch("config.settings") as mock_settings:
            mock_settings.agent_dir = "/test/agent"

            result = learn_from_interaction(
                query="What is the weather?",
                response="I don't know weather.",
                success=True,
            )

            assert result.get("should_save_solution") is None

    def test_learn_from_interaction_alias_mention(self) -> None:
        """Test learn_from_interaction detects alias clarification."""
        with patch("config.settings") as mock_settings:
            mock_settings.agent_dir = "/test/agent"

            result = learn_from_interaction(
                query="核心路由机是指哪些设备？",
                response="The core routers are...",
                success=True,
            )

            assert "should_update_aliases" in result
            assert result["should_update_aliases"] is True

    def test_learn_from_interaction_learning_count(self) -> None:
        """Test learn_from_interaction counts learnings."""
        with patch("config.settings") as mock_settings:
            mock_settings.agent_dir = "/test/agent"

            result = learn_from_interaction(
                query="网络故障，核心路由机是指哪些？",
                response="Let me help...",
                success=True,
            )

            # Should have 2 learnings (solution + aliases)
            assert result["learnings"] == "2"

    def test_learn_from_interaction_unsuccessful(self) -> None:
        """Test learn_from_interaction with unsuccessful interaction."""
        with patch("config.settings") as mock_settings:
            mock_settings.agent_dir = "/test/agent"

            result = learn_from_interaction(
                query="网络故障",
                response="I couldn't help.",
                success=False,
            )

            # Should not save solution if unsuccessful
            assert result.get("should_save_solution") is None


@pytest.mark.unit
class TestSuggestSolutionFilename:
    """Test suggest_solution_filename function."""

    def test_suggest_filename_problem_type_only(self) -> None:
        """Test suggest_solution_filename with only problem_type."""
        result = suggest_solution_filename("CRC")

        assert result == "crc"

    def test_suggest_filename_with_device(self) -> None:
        """Test suggest_solution_filename with problem_type and device."""
        result = suggest_solution_filename("CRC", "R1")

        assert result == "crc-r1"

    def test_suggest_filename_with_all_params(self) -> None:
        """Test suggest_solution_filename with all parameters."""
        result = suggest_solution_filename("CRC", "R1", "optical power")

        assert result == "crc-r1-optical-power"

    def test_suggest_filename_lowercases(self) -> None:
        """Test suggest_solution_filename converts to lowercase."""
        result = suggest_solution_filename("BGP", "R1")

        assert result == "bgp-r1"

    def test_suggest_filename_replaces_spaces(self) -> None:
        """Test suggest_solution_filename replaces spaces with hyphens."""
        result = suggest_solution_filename("CRC", "", "optical power low")

        assert "optical-power-low" in result

    def test_suggest_filename_truncates_long_symptom(self) -> None:
        """Test suggest_solution_filename truncates long symptoms."""
        long_symptom = "x" * 50
        result = suggest_solution_filename("CRC", "", long_symptom)

        # Should be truncated
        assert len(result.split("-")[-1]) <= 30

    def test_suggest_filename_empty_device(self) -> None:
        """Test suggest_solution_filename with empty device."""
        result = suggest_solution_filename("OSPF", "", "timer mismatch")

        assert result == "ospf-timer-mismatch"

    def test_suggest_filename_empty_symptom(self) -> None:
        """Test suggest_solution_filename with empty symptom."""
        result = suggest_solution_filename("BGP", "R1", "")

        assert result == "bgp-r1"


@pytest.mark.unit
class TestGetLearningGuidance:
    """Test get_learning_guidance function."""

    def test_get_learning_guidance_returns_string(self) -> None:
        """Test get_learning_guidance returns guidance text."""
        result = get_learning_guidance()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_learning_guidance_content(self) -> None:
        """Test get_learning_guidance has required content."""
        result = get_learning_guidance()

        assert "学习行为" in result
        assert "别名" in result
        assert "案例" in result
        assert "技能" in result

    def test_get_learning_guidance_structure(self) -> None:
        """Test get_learning_guidance has proper structure."""
        result = get_learning_guidance()

        # Should have markdown headers
        assert "##" in result
        # Should mention principles
        assert "原则" in result
