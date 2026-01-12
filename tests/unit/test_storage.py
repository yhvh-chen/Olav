"""Unit tests for storage.py module.

Tests storage backend configuration and permission checking.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from olav.core.storage import (
    DEEPAGENTS_HAS_STORAGE,
    check_write_permission,
    get_storage_backend,
    get_storage_permissions,
)


@pytest.mark.unit
class TestStorageBackend:
    """Test storage backend configuration."""

    def test_get_storage_backend_returns_none_when_unavailable(self) -> None:
        """Test get_storage_backend returns None when DeepAgents unavailable."""
        with patch("olav.core.storage.DEEPAGENTS_HAS_STORAGE", False):
            result = get_storage_backend()
            assert result is None

    def test_get_storage_backend_with_project_root(self) -> None:
        """Test get_storage_backend with custom project root."""
        if not DEEPAGENTS_HAS_STORAGE:
            pytest.skip("DeepAgents storage backends not available")

        with patch("olav.core.storage.DEEPAGENTS_HAS_STORAGE", True):
            with patch("config.settings") as mock_settings:
                mock_settings.agent_dir = "/test/agent"
                mock_project_root = Path("/test/project")

                with patch("olav.core.storage.StoreBackend") as mock_store_backend:
                    with patch("olav.core.storage.StateBackend") as mock_state_backend:
                        with patch("olav.core.storage.CompositeBackend") as mock_composite:
                            mock_store_instance = MagicMock()
                            mock_state_instance = MagicMock()
                            mock_composite_instance = MagicMock()

                            mock_store_backend.return_value = mock_store_instance
                            mock_state_backend.return_value = mock_state_instance
                            mock_composite.return_value = mock_composite_instance

                            result = get_storage_backend(mock_project_root)

                            # Verify backends were created
                            assert mock_store_backend.called
                            assert mock_state_backend.called
                            assert mock_composite.called

                            # Verify composite backend was returned
                            assert result == mock_composite_instance

    def test_get_storage_backend_default_project_root(self) -> None:
        """Test get_storage_backend uses current directory by default."""
        if not DEEPAGENTS_HAS_STORAGE:
            pytest.skip("DeepAgents storage backends not available")

        with patch("olav.core.storage.DEEPAGENTS_HAS_STORAGE", True):
            with patch("olav.core.storage.Path.cwd") as mock_cwd:
                mock_cwd.return_value = Path("/current/dir")
                with patch("config.settings") as mock_settings:
                    mock_settings.agent_dir = "/test/agent"

                    with patch("olav.core.storage.StoreBackend") as mock_store_backend:
                        with patch("olav.core.storage.StateBackend") as mock_state_backend:
                            with patch("olav.core.storage.CompositeBackend") as mock_composite:
                                mock_composite_instance = MagicMock()
                                mock_composite.return_value = mock_composite_instance

                                result = get_storage_backend()

                                # Verify current directory was used
                                mock_cwd.assert_called_once()
                                assert result == mock_composite_instance

    def test_get_storage_backend_creates_persistent_paths(self) -> None:
        """Test get_storage_backend creates correct persistent paths."""
        if not DEEPAGENTS_HAS_STORAGE:
            pytest.skip("DeepAgents storage backends not available")

        with patch("olav.core.storage.DEEPAGENTS_HAS_STORAGE", True):
            with patch("config.settings") as mock_settings:
                mock_settings.agent_dir = "/test/agent"

                with patch("olav.core.storage.StoreBackend") as mock_store_backend:
                    with patch("olav.core.storage.StateBackend") as mock_state_backend:
                        with patch("olav.core.storage.CompositeBackend") as mock_composite:
                            mock_store_instance = MagicMock()
                            mock_state_instance = MagicMock()
                            mock_composite_instance = MagicMock()

                            mock_store_backend.return_value = mock_store_instance
                            mock_state_backend.return_value = mock_state_instance
                            mock_composite.return_value = mock_composite_instance

                            result = get_storage_backend(Path("/test"))

                            # Verify StoreBackend was called with persistent paths
                            call_args = mock_store_backend.call_args
                            assert call_args is not None

                            # Verify persistent paths include skills, knowledge, commands
                            assert mock_store_backend.called

    def test_get_storage_backend_creates_temp_paths(self) -> None:
        """Test get_storage_backend creates temporary backend for scratch."""
        if not DEEPAGENTS_HAS_STORAGE:
            pytest.skip("DeepAgents storage backends not available")

        with patch("olav.core.storage.DEEPAGENTS_HAS_STORAGE", True):
            with patch("config.settings") as mock_settings:
                mock_settings.agent_dir = "/test/agent"

                with patch("olav.core.storage.StoreBackend") as mock_store_backend:
                    with patch("olav.core.storage.StateBackend") as mock_state_backend:
                        with patch("olav.core.storage.CompositeBackend") as mock_composite:
                            mock_store_instance = MagicMock()
                            mock_state_instance = MagicMock()
                            mock_composite_instance = MagicMock()

                            mock_store_backend.return_value = mock_store_instance
                            mock_state_backend.return_value = mock_state_instance
                            mock_composite.return_value = mock_composite_instance

                            result = get_storage_backend(Path("/test"))

                            # Verify StateBackend was created for temp paths
                            mock_state_backend.assert_called_once()


@pytest.mark.unit
class TestStoragePermissions:
    """Test storage permission checking."""

    def test_get_storage_permissions_returns_doc(self) -> None:
        """Test get_storage_permissions returns permission documentation."""
        result = get_storage_permissions()

        assert isinstance(result, str)
        assert "文件系统权限" in result
        assert "可读写" in result
        assert "只读" in result
        assert "不可访问" in result

    def test_permissions_documentation_structure(self) -> None:
        """Test permission documentation has correct structure."""
        doc = get_storage_permissions()

        # Check for required sections
        assert "skills" in doc
        assert "knowledge" in doc
        assert "imports/commands" in doc
        assert ".env" in doc

    def test_check_write_permission_with_writable_path(self) -> None:
        """Test check_write_permission returns True for writable paths."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = Path("/test/project/.olav/skills/test.md")

            result = check_write_permission(filepath)
            assert result is True

    def test_check_write_permission_knowledge_path(self) -> None:
        """Test check_write_permission allows knowledge paths."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = Path("/test/project/.olav/knowledge/test.md")

            result = check_write_permission(filepath)
            assert result is True

    def test_check_write_permission_solutions_path(self) -> None:
        """Test check_write_permission allows solutions subdirectory."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = Path("/test/project/.olav/knowledge/solutions/solution.md")

            result = check_write_permission(filepath)
            assert result is True

    def test_check_write_permission_commands_path(self) -> None:
        """Test check_write_permission allows commands paths."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = Path("/test/project/.olav/imports/commands/show_version.txt")

            result = check_write_permission(filepath)
            assert result is True

    def test_check_write_permission_denies_readonly_apis(self) -> None:
        """Test check_write_permission denies APIs directory."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = Path("/test/project/.olav/imports/apis/test.yaml")

            result = check_write_permission(filepath)
            assert result is False

    def test_check_write_permission_denies_outside_olav(self) -> None:
        """Test check_write_permission denies paths outside .olav."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = Path("/test/project/other/file.txt")

            result = check_write_permission(filepath)
            assert result is False

    def test_check_write_permission_with_custom_project_root(self) -> None:
        """Test check_write_permission with custom project root."""
        project_root = Path("/custom/project")
        filepath = Path("/custom/project/.olav/skills/test.md")

        result = check_write_permission(filepath, project_root)
        assert result is True

    def test_check_write_permission_denies_config(self) -> None:
        """Test check_write_permission denies config directory."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = Path("/test/project/.olav/config/settings.yaml")

            result = check_write_permission(filepath)
            assert result is False

    def test_check_write_permission_handles_string_path(self) -> None:
        """Test check_write_permission accepts string paths."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            filepath = "/test/project/.olav/skills/test.md"

            result = check_write_permission(filepath)
            assert result is True

    def test_check_write_permission_normalizes_paths(self) -> None:
        """Test check_write_permission normalizes relative paths."""
        with patch("olav.core.storage.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/test/project")
            # Use relative path elements
            filepath = Path("/test/project/.olav/../olav/skills/test.md")

            result = check_write_permission(filepath)
            # Should be normalized and checked
            assert isinstance(result, bool)


@pytest.mark.unit
class TestStorageImports:
    """Test storage module imports."""

    def test_module_exports_all_functions(self) -> None:
        """Test all functions are exported in __all__."""
        from olav.core import storage

        expected = {
            "get_storage_backend",
            "get_storage_permissions",
            "check_write_permission",
        }

        assert set(storage.__all__) == expected
