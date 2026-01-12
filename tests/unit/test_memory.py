"""Unit tests for memory module.

Tests for AgentMemory class that provides session persistence.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from olav.cli.memory import AgentMemory


# =============================================================================
# Test AgentMemory initialization
# =============================================================================


class TestAgentMemoryInit:
    """Tests for AgentMemory initialization."""

    def test_init_with_custom_memory_file(self, tmp_path):
        """Test initialization with custom memory file."""
        memory_file = tmp_path / "custom_memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        assert memory.memory_file == memory_file
        assert memory.max_messages == 100
        assert memory.messages == []
        assert memory.metadata == {}

    def test_init_with_custom_max_messages(self, tmp_path):
        """Test initialization with custom max_messages."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(max_messages=50, memory_file=str(memory_file))

        assert memory.max_messages == 50

    def test_init_loads_existing_memory(self, tmp_path):
        """Test that existing memory is loaded."""
        memory_file = tmp_path / "memory.json"
        memory_file.write_text(
            '{"messages": [{"role": "user", "content": "test"}], "metadata": {"key": "value"}}'
        )

        memory = AgentMemory(memory_file=str(memory_file))

        assert len(memory.messages) == 1
        assert memory.messages[0]["content"] == "test"
        assert memory.metadata["key"] == "value"

    def test_init_handles_corrupt_file(self, tmp_path):
        """Test handling of corrupt memory file."""
        memory_file = tmp_path / "memory.json"
        memory_file.write_text("invalid json {{{")

        memory = AgentMemory(memory_file=str(memory_file))

        assert memory.messages == []
        assert memory.metadata == {}

    def test_init_creates_directory(self, tmp_path):
        """Test that directory is created if it doesn't exist."""
        memory_file = tmp_path / "subdir" / "memory.json"

        memory = AgentMemory(memory_file=str(memory_file))

        assert memory_file.parent.exists()
        assert memory_file.parent.is_dir()

    @patch("config.settings.settings")
    def test_init_uses_settings_default(self, mock_settings, tmp_path):
        """Test that settings.agent_dir is used when no custom file."""
        mock_settings.agent_dir = str(tmp_path)

        memory = AgentMemory()

        assert memory.memory_file == tmp_path / ".agent_memory.json"

    def test_init_uses_class_memory_file(self, tmp_path):
        """Test initialization uses MEMORY_FILE class variable when set."""
        memory_file = tmp_path / "class_memory.json"
        AgentMemory.MEMORY_FILE = memory_file

        try:
            memory = AgentMemory()

            assert memory.memory_file == memory_file
        finally:
            AgentMemory.MEMORY_FILE = None


# =============================================================================
# Test _load method
# =============================================================================


class TestLoad:
    """Tests for _load method."""

    def test_load_creates_new_file(self, tmp_path):
        """Test loading when file doesn't exist creates it."""
        memory_file = tmp_path / "new_memory.json"

        memory = AgentMemory(memory_file=str(memory_file))

        assert memory.messages == []
        assert memory.metadata == {}

    def test_load_with_empty_file(self, tmp_path):
        """Test loading from empty file."""
        memory_file = tmp_path / "empty.json"
        memory_file.write_text("{}")

        memory = AgentMemory(memory_file=str(memory_file))

        assert memory.messages == []
        assert memory.metadata == {}

    def test_load_with_multiple_messages(self, tmp_path):
        """Test loading multiple messages."""
        memory_file = tmp_path / "memory.json"
        memory_file.write_text(
            """{
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
                {"role": "user", "content": "How are you?"}
            ],
            "metadata": {"session_id": "123"}
        }"""
        )

        memory = AgentMemory(memory_file=str(memory_file))

        assert len(memory.messages) == 3
        assert memory.messages[0]["role"] == "user"
        assert memory.messages[1]["content"] == "Hi there"
        assert memory.metadata["session_id"] == "123"


# =============================================================================
# Test save method
# =============================================================================


class TestSave:
    """Tests for save method."""

    def test_save_persists_messages(self, tmp_path):
        """Test that messages are persisted."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": "test1"},
            {"role": "assistant", "content": "test2"},
        ]

        memory.save()

        content = memory_file.read_text()
        assert "test1" in content
        assert "test2" in content

    def test_save_persists_metadata(self, tmp_path):
        """Test that metadata is persisted."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.metadata = {"key": "value", "count": 42}

        memory.save()

        content = memory_file.read_text()
        assert '"key": "value"' in content
        assert '"count": 42' in content

    def test_save_trims_to_max_messages(self, tmp_path):
        """Test that save trims messages to max_messages."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(max_messages=3, memory_file=str(memory_file))

        # Add 5 messages
        for i in range(5):
            memory.messages.append({"role": "user", "content": f"message{i}"})

        memory.save()

        # Should only keep last 3
        assert len(memory.messages) == 3
        assert memory.messages[0]["content"] == "message2"
        assert memory.messages[2]["content"] == "message4"


# =============================================================================
# Test add method
# =============================================================================


class TestAdd:
    """Tests for add method."""

    def test_add_message(self, tmp_path):
        """Test adding a message."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        memory.add("user", "Hello world")

        assert len(memory.messages) == 1
        assert memory.messages[0]["role"] == "user"
        assert memory.messages[0]["content"] == "Hello world"

    def test_add_with_extra_metadata(self, tmp_path):
        """Test adding message with extra metadata."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        memory.add("tool", "Command output", tool_name="show_version", device="R1")

        assert memory.messages[0]["role"] == "tool"
        assert memory.messages[0]["tool_name"] == "show_version"
        assert memory.messages[0]["device"] == "R1"

    def test_add_saves_automatically(self, tmp_path):
        """Test that add saves automatically."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        memory.add("user", "test")

        # Should be persisted
        assert memory_file.exists()
        content = memory_file.read_text()
        assert "test" in content


# =============================================================================
# Test clear method
# =============================================================================


class TestClear:
    """Tests for clear method."""

    def test_clear_messages_and_metadata(self, tmp_path):
        """Test clearing messages and metadata."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [{"role": "user", "content": "test"}]
        memory.metadata = {"key": "value"}

        memory.clear()

        assert memory.messages == []
        assert memory.metadata == {}

    def test_clear_persists(self, tmp_path):
        """Test that clear persists to file."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [{"role": "user", "content": "test"}]
        memory.metadata = {"key": "value"}

        memory.clear()

        # Load again and verify it's still empty
        memory2 = AgentMemory(memory_file=str(memory_file))
        assert memory2.messages == []
        assert memory2.metadata == {}


# =============================================================================
# Test get_context method
# =============================================================================


class TestGetContext:
    """Tests for get_context method."""

    def test_get_context_all_messages(self, tmp_path):
        """Test getting all messages."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ]

        context = memory.get_context()

        assert len(context) == 2
        assert context == memory.messages

    def test_get_context_with_limit(self, tmp_path):
        """Test getting limited messages."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": f"msg{i}"} for i in range(10)
        ]

        context = memory.get_context(max_messages=3)

        assert len(context) == 3
        assert context[0]["content"] == "msg7"  # Last 3
        assert context[2]["content"] == "msg9"

    def test_get_context_returns_copy(self, tmp_path):
        """Test that get_context returns a copy, not reference."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [{"role": "user", "content": "test"}]

        context = memory.get_context()
        context.append({"role": "system", "content": "injected"})

        # Original should be unchanged
        assert len(memory.messages) == 1


# =============================================================================
# Test set_metadata and get_metadata
# =============================================================================


class TestMetadata:
    """Tests for metadata methods."""

    def test_set_get_metadata(self, tmp_path):
        """Test setting and getting metadata."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        memory.set_metadata("session_id", "12345")
        value = memory.get_metadata("session_id")

        assert value == "12345"

    def test_get_metadata_default(self, tmp_path):
        """Test getting non-existent metadata returns default."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        value = memory.get_metadata("nonexistent", default="default_value")

        assert value == "default_value"

    def test_get_metadata_no_default(self, tmp_path):
        """Test getting non-existent metadata without default returns None."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        value = memory.get_metadata("nonexistent")

        assert value is None

    def test_set_metadata_saves(self, tmp_path):
        """Test that set_metadata saves automatically."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        memory.set_metadata("key", "value")

        # Load again and verify
        memory2 = AgentMemory(memory_file=str(memory_file))
        assert memory2.get_metadata("key") == "value"


# =============================================================================
# Test get_stats method
# =============================================================================


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats_empty_memory(self, tmp_path):
        """Test stats for empty memory."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))

        stats = memory.get_stats()

        assert stats["total_messages"] == 0
        assert stats["user_messages"] == 0
        assert stats["assistant_messages"] == 0
        assert stats["tool_messages"] == 0
        assert stats["max_messages"] == 100
        assert stats["memory_file"] == str(memory_file)

    def test_get_stats_counts_roles(self, tmp_path):
        """Test stats counts messages by role."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": "u1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a1"},
            {"role": "tool", "content": "t1"},
            {"role": "user", "content": "u3"},
        ]

        stats = memory.get_stats()

        assert stats["total_messages"] == 5
        assert stats["user_messages"] == 3
        assert stats["assistant_messages"] == 1
        assert stats["tool_messages"] == 1

    def test_get_stats_custom_max(self, tmp_path):
        """Test stats with custom max_messages."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(max_messages=50, memory_file=str(memory_file))

        stats = memory.get_stats()

        assert stats["max_messages"] == 50


# =============================================================================
# Test get_conversation_messages
# =============================================================================


class TestGetConversationMessages:
    """Tests for get_conversation_messages method."""

    def test_get_conversation_messages_basic(self, tmp_path):
        """Test getting conversation messages for LangChain."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        result = memory.get_conversation_messages()

        assert len(result) == 2
        assert result[0] == ("user", "Hello")
        assert result[1] == ("assistant", "Hi there")

    def test_get_conversation_messages_skips_tool(self, tmp_path):
        """Test that tool messages are filtered out."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": "Run command"},
            {"role": "tool", "content": "Command output"},
            {"role": "assistant", "content": "Done"},
        ]

        result = memory.get_conversation_messages()

        assert len(result) == 2
        assert result[0] == ("user", "Run command")
        assert result[1] == ("assistant", "Done")

    def test_get_conversation_messages_limits_turns(self, tmp_path):
        """Test max_turns parameter."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        # Create 10 turns (20 messages)
        for i in range(10):
            memory.messages.append({"role": "user", "content": f"u{i}"})
            memory.messages.append({"role": "assistant", "content": f"a{i}"})

        result = memory.get_conversation_messages(max_turns=3)

        # Should only get last 3 turns (6 messages)
        assert len(result) == 6
        assert result[0][1] == "u7"
        assert result[-1][1] == "a9"

    def test_get_conversation_messages_truncates_long(self, tmp_path):
        """Test that long messages are truncated."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": "x" * 2500},
        ]

        result = memory.get_conversation_messages()

        assert len(result) == 1
        assert len(result[0][1]) == 1800 + len("\n... [truncated]")
        assert "[truncated]" in result[0][1]

    def test_get_conversation_messages_respects_char_limit(self, tmp_path):
        """Test max_chars parameter adds truncation summary."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": "a" * 3000},
            {"role": "assistant", "content": "b" * 3000},
        ]

        result = memory.get_conversation_messages(max_chars=4000)

        # First message should be included (truncated), second should hit limit
        assert len(result) >= 1
        # Check that truncation summary is added when limit hit
        if len(result) > 1:
            assert any("truncated" in r[1].lower() for r in result)

    def test_get_conversation_messages_defaults_role(self, tmp_path):
        """Test that missing role defaults to 'user'."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"content": "No role specified"},
        ]

        result = memory.get_conversation_messages()

        assert len(result) == 1
        assert result[0] == ("user", "No role specified")

    def test_get_conversation_messages_empty_content(self, tmp_path):
        """Test handling of empty content."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        memory.messages = [
            {"role": "user", "content": ""},
        ]

        result = memory.get_conversation_messages()

        assert len(result) == 1
        assert result[0] == ("user", "")

    def test_get_conversation_messages_adds_truncation_summary(self, tmp_path):
        """Test that truncation summary is inserted when char limit hit."""
        memory_file = tmp_path / "memory.json"
        memory = AgentMemory(memory_file=str(memory_file))
        # First message 1000 chars, second message after truncation ~1816 chars
        # Total would be ~2816 > 2500, so summary should be inserted
        memory.messages = [
            {"role": "user", "content": "x" * 1000},
            {"role": "assistant", "content": "y" * 3000},
        ]

        result = memory.get_conversation_messages(max_chars=2500)

        # First message added (1000 chars), second truncated to 1816, total would be 2816 > 2500
        # So summary is inserted at position 0, then break
        assert len(result) == 2
        # First should be the summary (inserted at position 0)
        assert result[0][0] == "system"
        assert "truncated" in result[0][1].lower()
        # Second should be the first message
        assert result[1][0] == "user"
        assert len(result[1][1]) == 1000
