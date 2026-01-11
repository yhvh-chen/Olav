"""Agent Memory - Session persistence for OLAV agent.

Provides persistent storage for conversation history across CLI sessions.
"""

import json
from pathlib import Path
from typing import Any


class AgentMemory:
    """Session memory persistence for OLAV agent.

    Stores conversation history and context between CLI sessions.
    Memory is persisted to agent_dir/.agent_memory.json
    """

    MEMORY_FILE = None  # Set dynamically in __init__

    def __init__(self, max_messages: int = 100, memory_file: str | Path | None = None) -> None:
        """Initialize agent memory.

        Args:
            max_messages: Maximum number of messages to keep
            memory_file: Custom memory file path (defaults to agent_dir/.agent_memory.json)
        """
        self.max_messages = max_messages

        if memory_file:
            self.memory_file = Path(memory_file)
        elif self.MEMORY_FILE:
            self.memory_file = self.MEMORY_FILE
        else:
            from config.settings import settings
            self.memory_file = Path(settings.agent_dir) / ".agent_memory.json"

        self.messages: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load memory from file."""
        if self.memory_file.exists():
            try:
                content = self.memory_file.read_text()
                data = json.loads(content)
                self.messages = data.get("messages", [])
                self.metadata = data.get("metadata", {})
            except (json.JSONDecodeError, KeyError):
                # Corrupt file, start fresh
                self.messages = []
                self.metadata = {}
        else:
            # Ensure directory exists
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        """Save memory to file."""
        # Keep only recent messages
        self.messages = self.messages[-self.max_messages :]

        data = {
            "messages": self.messages,
            "metadata": self.metadata,
        }

        self.memory_file.write_text(json.dumps(data, indent=2))

    def add(self, role: str, content: str, **kwargs) -> None:
        """Add a message to memory.

        Args:
            role: Message role (user, assistant, system, tool)
            content: Message content
            **kwargs: Additional metadata (tool_name, device, etc.)
        """
        message = {
            "role": role,
            "content": content,
            **kwargs,
        }
        self.messages.append(message)
        self.save()

    def clear(self) -> None:
        """Clear all messages and metadata."""
        self.messages = []
        self.metadata = {}
        self.save()

    def get_context(self, max_messages: int | None = None) -> list[dict[str, Any]]:
        """Get conversation context for agent.

        Args:
            max_messages: Maximum messages to return (default: all)

        Returns:
            List of message dictionaries
        """
        if max_messages is None:
            return self.messages.copy()
        return self.messages[-max_messages:]

    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata value.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self.metadata[key] = value
        self.save()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value.

        Args:
            key: Metadata key
            default: Default value if key not found

        Returns:
            Metadata value or default
        """
        return self.metadata.get(key, default)

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics.

        Returns:
            Dictionary with memory stats
        """
        user_messages = sum(1 for m in self.messages if m.get("role") == "user")
        assistant_messages = sum(
            1 for m in self.messages if m.get("role") == "assistant"
        )
        tool_messages = sum(1 for m in self.messages if m.get("role") == "tool")

        return {
            "total_messages": len(self.messages),
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "tool_messages": tool_messages,
            "max_messages": self.max_messages,
            "memory_file": str(self.memory_file),
        }
