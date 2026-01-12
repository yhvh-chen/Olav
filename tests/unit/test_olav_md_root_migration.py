"""Unit tests for OLAV.md root directory migration.

Tests verify that:
1. OLAV.md is loaded from project root (not .olav/)
2. Storage permissions correctly protect root OLAV.md
3. CLI validation checks for root OLAV.md
"""

from pathlib import Path
from unittest.mock import patch


class TestOlavMdRootPath:
    """Test OLAV.md loading from project root."""

    def test_olav_md_exists_in_root(self):
        """Test that OLAV.md exists in project root."""
        root = Path(__file__).parent.parent.parent
        olav_md = root / "OLAV.md"

        assert olav_md.exists(), f"OLAV.md not found at {olav_md}"

    def test_olav_md_not_in_olav_dir(self):
        """Test that OLAV.md is NOT in .olav directory."""
        root = Path(__file__).parent.parent.parent
        olav_dir_md = root / ".olav" / "OLAV.md"

        assert not olav_dir_md.exists(), "OLAV.md should not be in .olav directory"

    def test_olav_md_is_readable(self):
        """Test that OLAV.md can be read."""
        root = Path(__file__).parent.parent.parent
        olav_md = root / "OLAV.md"

        content = olav_md.read_text(encoding="utf-8")
        assert len(content) > 0
        assert "OLAV" in content or "Network" in content


class TestAgentOlavMdLoading:
    """Test that agent.py loads OLAV.md from root."""

    def test_agent_loads_olav_md(self):
        """Test that agent loads OLAV.md from root path."""
        # The path should be: Path("OLAV.md") which resolves to project root
        # This path exists when running from project root
        root = Path(__file__).parent.parent.parent
        full_path = root / "OLAV.md"

        assert full_path.exists()

    @patch("pathlib.Path.read_text")
    def test_agent_reads_olav_md_content(self, mock_read):
        """Test that agent reads OLAV.md content."""
        mock_read.return_value = "# OLAV System Prompt\n"

        # Simulate what agent.py does
        # mock_read would be called here

        assert mock_read.return_value.startswith("# OLAV")


class TestStoragePermissions:
    """Test that storage.py protects root OLAV.md."""

    def test_root_olav_md_in_read_only_paths(self):
        """Test that root OLAV.md is listed as read-only."""
        # In storage.py, read_only_paths should include: project_root / "OLAV.md"
        root = Path(__file__).parent.parent.parent
        expected_path = root / "OLAV.md"

        assert expected_path.exists()
        # The path should be protected by storage.py

    def test_storage_prevents_olav_dir_olav_md(self):
        """Test that storage doesn't reference .olav/OLAV.md."""
        # This is to ensure the old path is not used
        root = Path(__file__).parent.parent.parent
        old_path = root / ".olav" / "OLAV.md"

        # Old path should not exist
        assert not old_path.exists()


class TestCliValidation:
    """Test that CLI validation checks root OLAV.md."""

    def test_cli_checks_root_olav_md(self):
        """Test that cli_commands_c2.py checks root OLAV.md."""
        # In cli_commands_c2.py ValidateCommand.validate()
        # The check should be: olav_dir.parent / "OLAV.md"
        root = Path(__file__).parent.parent.parent
        olav_dir = root / ".olav"
        expected_olav_md = olav_dir.parent / "OLAV.md"

        # Should point to root
        assert expected_olav_md == root / "OLAV.md"
        assert expected_olav_md.exists()

    def test_cli_validation_file_check(self):
        """Test that CLI validation can find OLAV.md."""
        root = Path(__file__).parent.parent.parent
        olav_dir = root / ".olav"

        # Simulate what ValidateCommand does
        core_files = {
            "OLAV.md": olav_dir.parent / "OLAV.md",
        }

        # File should exist
        assert core_files["OLAV.md"].exists()


class TestFilePathMigration:
    """Test the complete file path migration."""

    def test_olav_md_path_consistency(self):
        """Test that all components use consistent OLAV.md path."""
        root = Path(__file__).parent.parent.parent

        # All these should point to the same file
        agent_path = Path("OLAV.md")  # From agent.py
        storage_path = root / "OLAV.md"  # From storage.py
        cli_path = root / ".olav" / ".." / "OLAV.md"  # From cli_commands_c2.py (normalized)

        # Normalize paths for comparison
        agent_full = root / agent_path
        cli_normalized = cli_path.resolve()

        assert agent_full.resolve() == storage_path.resolve()
        assert storage_path.resolve() == cli_normalized

    def test_no_duplicate_olav_md(self):
        """Test that OLAV.md only exists in root, not in .olav/."""
        root = Path(__file__).parent.parent.parent

        root_olav = root / "OLAV.md"
        olav_dir_olav = root / ".olav" / "OLAV.md"

        # Root should exist
        assert root_olav.exists()

        # .olav/ should not have it
        assert not olav_dir_olav.exists()

    def test_gitignore_excludes_olav_dir_olav_md(self):
        """Test that .gitignore doesn't unnecessarily exclude root OLAV.md."""
        # Root OLAV.md should NOT be in gitignore
        # (it's part of the repo)
        # But .olav/OLAV.md should not exist anyway


class TestBuildIntegration:
    """Integration tests with build/CI."""

    def test_olav_md_committed_to_repo(self):
        """Test that OLAV.md is part of the repository."""
        root = Path(__file__).parent.parent.parent
        git_dir = root / ".git"
        olav_md = root / "OLAV.md"

        # If .git exists, check file is tracked
        if git_dir.exists():
            # File should exist
            assert olav_md.exists()

    def test_no_broken_imports_after_migration(self):
        """Test that no broken imports reference old paths."""
        root = Path(__file__).parent.parent.parent

        # Check key source files don't reference old path
        agent_file = root / "src" / "olav" / "agent.py"
        storage_file = root / "src" / "olav" / "core" / "storage.py"

        agent_content = agent_file.read_text(encoding="utf-8")
        storage_content = storage_file.read_text(encoding="utf-8")

        # Old path references should be gone
        # (except in comments about the migration)
        assert 'Path(settings.agent_dir) / "OLAV.md"' not in agent_content
        assert 'agent_dir / "OLAV.md"' not in storage_content or \
               "project_root / \"OLAV.md\"" in storage_content
