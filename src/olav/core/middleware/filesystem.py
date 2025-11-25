"""Filesystem middleware for tool result caching and file operations.

Lightweight abstraction extracted from DeepAgents framework (archive/deepagents/).
Provides secure file operations with audit logging and HITL intercepts.

Key differences from DeepAgents original:
- Uses LangGraph StateBackend instead of custom BackendProtocol
- Simplified state management (no complex reducers)
- Integrated OpenSearch audit logging
- HITL intercepts for write/delete operations
"""

import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger(__name__)


# Constants (from DeepAgents)
MAX_LINE_LENGTH = 2000
LINE_NUMBER_WIDTH = 6
DEFAULT_READ_OFFSET = 0
DEFAULT_READ_LIMIT = 500

EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"


class FilesystemMiddleware:
    """File operation abstraction with StateBackend and audit logging.

    Provides:
    - read_file(): Read content with line range support
    - write_file(): Write content with HITL approval
    - list_files(): List files with glob patterns
    - delete_file(): Delete with HITL approval

    Security features:
    - Path validation (prevent traversal attacks)
    - HITL intercepts for write/delete
    - OpenSearch audit logging

    Args:
        checkpointer: LangGraph checkpointer (StateBackend)
        workspace_root: Root directory for file operations (default: "./data/generated_configs")
        audit_enabled: Whether to log operations to OpenSearch (default: True)
        hitl_enabled: Whether to require approval for write/delete (default: True)

    Example:
        >>> fs = FilesystemMiddleware(checkpointer, workspace_root="./data/cache")
        >>> content = await fs.read_file("tool_results/abc123.json")
        >>> await fs.write_file("config/router1.txt", "interface eth0...")
    """

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver,
        workspace_root: str = "./data/generated_configs",
        audit_enabled: bool = True,
        hitl_enabled: bool = True,
    ) -> None:
        """Initialize filesystem middleware.

        Args:
            checkpointer: LangGraph checkpoint saver (StateBackend)
            workspace_root: Root path for file operations
            audit_enabled: Enable OpenSearch audit logging
            hitl_enabled: Require HITL approval for write/delete
        """
        self.checkpointer = checkpointer
        self.workspace_root = Path(workspace_root).resolve()
        self.audit_enabled = audit_enabled
        self.hitl_enabled = hitl_enabled

        # Ensure workspace exists
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        logger.info(
            "FilesystemMiddleware initialized",
            extra={
                "workspace_root": str(self.workspace_root),
                "audit_enabled": audit_enabled,
                "hitl_enabled": hitl_enabled,
            },
        )

    def _validate_path(
        self,
        path: str,
        allowed_prefixes: Sequence[str] | None = None,
    ) -> Path:
        """Validate and normalize file path (security check).

        Prevents path traversal attacks (../, ~/, absolute paths).

        Args:
            path: Path to validate
            allowed_prefixes: Optional list of allowed path prefixes

        Returns:
            Normalized absolute Path object

        Raises:
            ValueError: If path contains traversal patterns or escapes workspace

        Examples:
            >>> fs._validate_path("tool_results/abc.json")
            Path("c:/olav/data/generated_configs/tool_results/abc.json")

            >>> fs._validate_path("../../etc/passwd")  # Raises ValueError
        """
        # Prevent path traversal
        if ".." in path or path.startswith("~"):
            msg = f"Path traversal not allowed: {path}"
            raise ValueError(msg)

        # Normalize to absolute path
        normalized = Path(path.replace("\\", "/"))
        if not normalized.is_absolute():
            normalized = self.workspace_root / normalized
        normalized = normalized.resolve()

        # Ensure path is within workspace
        try:
            normalized.relative_to(self.workspace_root)
        except ValueError as e:
            msg = f"Path escapes workspace root: {normalized} not in {self.workspace_root}"
            raise ValueError(msg) from e

        # Check allowed prefixes if specified
        if allowed_prefixes:
            relative = normalized.relative_to(self.workspace_root)
            if not any(str(relative).startswith(prefix) for prefix in allowed_prefixes):
                msg = f"Path not in allowed prefixes: {relative} not in {allowed_prefixes}"
                raise ValueError(msg)

        return normalized

    def _format_line_number(self, line_num: int) -> str:
        """Format line number with padding (DeepAgents style)."""
        return f"{line_num:>{LINE_NUMBER_WIDTH}}"

    async def _audit_log(
        self,
        operation: Literal["read", "write", "list", "delete"],
        path: str,
        success: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log file operation to OpenSearch audit index.

        Args:
            operation: Operation type
            path: File path
            success: Whether operation succeeded
            metadata: Additional metadata (e.g., error message, line range)
        """
        if not self.audit_enabled:
            return

        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "operation": operation,
            "path": path,
            "success": success,
            "metadata": metadata or {},
        }

        # TODO: Implement OpenSearch client integration
        # For now, just log to structured logger
        logger.info(
            f"Filesystem audit: {operation} {path}",
            extra={"audit": audit_entry},
        )

    async def _request_hitl_approval(
        self,
        operation: Literal["write", "delete"],
        path: str,
        content: str | None = None,
    ) -> bool:
        """Request HITL approval for write/delete operations.

        Args:
            operation: Operation type
            path: File path
            content: Content to write (for write operations)

        Returns:
            True if approved, False if rejected

        Raises:
            NotImplementedError: HITL approval not yet implemented
        """
        if not self.hitl_enabled:
            return True

        # TODO: Implement LangGraph interrupt for HITL approval
        # This should trigger a LangGraph Command interrupt that pauses workflow
        # and waits for user approval via CLI/WebUI

        logger.warning(
            f"HITL approval required for {operation} {path} (auto-approved for now)",
            extra={
                "operation": operation,
                "path": path,
                "content_preview": content[:200] if content else None,
            },
        )

        # Auto-approve for now (TODO: implement real HITL)
        return True

    async def read_file(
        self,
        path: str,
        start_line: int = DEFAULT_READ_OFFSET,
        num_lines: int | None = None,
    ) -> str:
        """Read file content with optional line range.

        Args:
            path: File path (relative to workspace_root or absolute)
            start_line: Starting line number (0-indexed)
            num_lines: Number of lines to read (None = all remaining lines)

        Returns:
            File content as string (with line numbers if partial read)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path is invalid

        Examples:
            >>> await fs.read_file("tool_results/abc.json")
            '{"result": "success"}'

            >>> await fs.read_file("large_file.txt", start_line=100, num_lines=50)
            '   101 line content here\\n   102 next line...'
        """
        normalized_path = self._validate_path(path)

        try:
            if not normalized_path.exists():
                await self._audit_log("read", str(path), False, {"error": "not_found"})
                msg = f"File not found: {path}"
                raise FileNotFoundError(msg)

            with open(normalized_path, encoding="utf-8") as f:
                lines = f.readlines()

            # Handle empty file
            if not lines:
                await self._audit_log("read", str(path), True, {"warning": "empty_file"})
                return EMPTY_CONTENT_WARNING

            # Apply line range
            end_line = start_line + num_lines if num_lines else len(lines)
            selected_lines = lines[start_line:end_line]

            # Format with line numbers if partial read
            if start_line > 0 or end_line < len(lines):
                formatted_lines = [
                    f"{self._format_line_number(i + start_line + 1)} {line.rstrip()}"
                    for i, line in enumerate(selected_lines)
                ]
                content = "\n".join(formatted_lines)
            else:
                content = "".join(selected_lines)

            await self._audit_log(
                "read",
                str(path),
                True,
                {"start_line": start_line, "num_lines": len(selected_lines)},
            )

            return content

        except FileNotFoundError:
            raise
        except Exception as e:
            await self._audit_log("read", str(path), False, {"error": str(e)})
            logger.error(f"Failed to read file {path}: {e}")
            raise

    async def write_file(
        self,
        path: str,
        content: str,
        create_dirs: bool = True,
    ) -> None:
        """Write content to file with HITL approval.

        Args:
            path: File path (relative to workspace_root or absolute)
            content: Content to write
            create_dirs: Whether to create parent directories

        Raises:
            ValueError: If path is invalid or HITL approval denied
            IOError: If write operation fails

        Examples:
            >>> await fs.write_file("config/router1.txt", "interface eth0\\n...")
            >>> await fs.write_file("tool_results/cache.json", json.dumps(result))
        """
        normalized_path = self._validate_path(path)

        # Request HITL approval
        approved = await self._request_hitl_approval("write", str(path), content)
        if not approved:
            await self._audit_log("write", str(path), False, {"error": "hitl_rejected"})
            msg = f"HITL approval denied for write: {path}"
            raise ValueError(msg)

        try:
            # Create parent directories if needed
            if create_dirs:
                normalized_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            with open(normalized_path, "w", encoding="utf-8") as f:
                f.write(content)

            await self._audit_log(
                "write",
                str(path),
                True,
                {"size_bytes": len(content.encode("utf-8"))},
            )

            logger.info(f"Wrote file: {path}")

        except Exception as e:
            await self._audit_log("write", str(path), False, {"error": str(e)})
            logger.error(f"Failed to write file {path}: {e}")
            raise

    async def list_files(
        self,
        pattern: str = "*",
        recursive: bool = False,
    ) -> list[str]:
        """List files matching glob pattern.

        Args:
            pattern: Glob pattern (e.g., "*.json", "tool_results/*.txt")
            recursive: Whether to search recursively

        Returns:
            List of file paths (relative to workspace_root)

        Examples:
            >>> await fs.list_files("tool_results/*.json")
            ["tool_results/abc123.json", "tool_results/def456.json"]

            >>> await fs.list_files("**/*.txt", recursive=True)
            ["config/router1.txt", "logs/debug.txt"]
        """
        try:
            # Use pathlib glob
            if recursive:
                matches = self.workspace_root.glob(f"**/{pattern}")
            else:
                matches = self.workspace_root.glob(pattern)

            # Filter only files (not directories)
            files = [str(p.relative_to(self.workspace_root)) for p in matches if p.is_file()]

            await self._audit_log(
                "list",
                pattern,
                True,
                {"recursive": recursive, "count": len(files)},
            )

            return sorted(files)

        except Exception as e:
            await self._audit_log("list", pattern, False, {"error": str(e)})
            logger.error(f"Failed to list files {pattern}: {e}")
            raise

    async def delete_file(
        self,
        path: str,
    ) -> None:
        """Delete file with HITL approval.

        Args:
            path: File path (relative to workspace_root or absolute)

        Raises:
            ValueError: If path is invalid or HITL approval denied
            FileNotFoundError: If file doesn't exist

        Examples:
            >>> await fs.delete_file("tool_results/old_cache.json")
        """
        normalized_path = self._validate_path(path)

        # Request HITL approval
        approved = await self._request_hitl_approval("delete", str(path))
        if not approved:
            await self._audit_log("delete", str(path), False, {"error": "hitl_rejected"})
            msg = f"HITL approval denied for delete: {path}"
            raise ValueError(msg)

        try:
            if not normalized_path.exists():
                await self._audit_log("delete", str(path), False, {"error": "not_found"})
                msg = f"File not found: {path}"
                raise FileNotFoundError(msg)

            normalized_path.unlink()

            await self._audit_log("delete", str(path), True)
            logger.info(f"Deleted file: {path}")

        except FileNotFoundError:
            raise
        except Exception as e:
            await self._audit_log("delete", str(path), False, {"error": str(e)})
            logger.error(f"Failed to delete file {path}: {e}")
            raise

    def get_cache_key(self, query: str) -> str:
        """Generate cache key from query string.

        Uses SHA256 hash for consistent, collision-resistant keys.

        Args:
            query: Query string to hash

        Returns:
            Cache key (e.g., "tool_results/abc123def456.json")

        Examples:
            >>> fs.get_cache_key("show ip bgp summary")
            "tool_results/3f2a1b9c8d7e6f5a4b3c2d1e0f9a8b7c.json"
        """
        hash_obj = hashlib.sha256(query.encode("utf-8"))
        cache_hash = hash_obj.hexdigest()[:32]  # First 32 chars
        return f"tool_results/{cache_hash}.json"

    async def cache_tool_result(
        self,
        query: str,
        result: dict[str, Any],
    ) -> None:
        """Cache tool execution result.

        Args:
            query: Query string (used for cache key)
            result: Tool execution result (must be JSON-serializable)

        Examples:
            >>> await fs.cache_tool_result("show version", {"output": "Cisco IOS..."})
        """
        cache_key = self.get_cache_key(query)
        content = json.dumps(result, indent=2, ensure_ascii=False)
        await self.write_file(cache_key, content)

    async def get_cached_result(
        self,
        query: str,
    ) -> dict[str, Any] | None:
        """Retrieve cached tool result.

        Args:
            query: Query string (used for cache key)

        Returns:
            Cached result if exists, None otherwise

        Examples:
            >>> cached = await fs.get_cached_result("show version")
            >>> if cached:
            ...     return cached["output"]
        """
        cache_key = self.get_cache_key(query)

        try:
            content = await self.read_file(cache_key)
            if content == EMPTY_CONTENT_WARNING:
                return None
            return json.loads(content)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in cache {cache_key}: {e}")
            return None
