"""
Unit tests for loader module.

Tests for capabilities loader that loads CLI commands and API definitions from imports/ directory.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from olav.tools.loader import (
    APIEndpoint,
    CapabilitiesLoader,
    CommandFileFormat,
    reload_capabilities,
    validate_capabilities,
)


# =============================================================================
# Test Pydantic models
# =============================================================================


class TestCommandFileFormat:
    """Tests for CommandFileFormat model."""

    def test_command_file_format_valid(self):
        """Test valid command file format."""
        data = {"lines": ["show run", "show ip int brief"]}
        model = CommandFileFormat(**data)

        assert model.lines == ["show run", "show ip int brief"]

    def test_command_file_format_empty_lines(self):
        """Test command file format with empty lines."""
        data = {"lines": []}
        model = CommandFileFormat(**data)

        assert model.lines == []


class TestAPIEndpoint:
    """Tests for APIEndpoint model."""

    def test_api_endpoint_valid(self):
        """Test valid API endpoint."""
        data = {
            "path": "/api/devices/",
            "method": "GET",
            "summary": "List devices",
        }
        endpoint = APIEndpoint(**data)

        assert endpoint.path == "/api/devices/"
        assert endpoint.method == "GET"
        assert endpoint.summary == "List devices"
        assert endpoint.is_write is False

    def test_api_endpoint_with_write_flag(self):
        """Test API endpoint with write flag."""
        data = {
            "path": "/api/devices/{id}/",
            "method": "PATCH",
            "is_write": True,
        }
        endpoint = APIEndpoint(**data)

        assert endpoint.is_write is True

    def test_api_endpoint_with_parameters(self):
        """Test API endpoint with parameters."""
        data = {
            "path": "/api/devices/",
            "method": "GET",
            "parameters": {"limit": 10},
        }
        endpoint = APIEndpoint(**data)

        assert endpoint.parameters == {"limit": 10}


# =============================================================================
# Test CapabilitiesLoader
# =============================================================================


class TestCapabilitiesLoaderInit:
    """Tests for CapabilitiesLoader initialization."""

    def test_init_with_path(self):
        """Test initialization with path."""
        imports_dir = Path("/test/imports")

        loader = CapabilitiesLoader(imports_dir)

        assert loader.imports_dir == imports_dir
        assert loader.db is None

    def test_init_with_database(self):
        """Test initialization with database."""
        imports_dir = Path("/test/imports")
        mock_db = Mock()

        loader = CapabilitiesLoader(imports_dir, database=mock_db)

        assert loader.imports_dir == imports_dir
        assert loader.db == mock_db

    def test_init_with_string_path(self):
        """Test initialization with string path."""
        loader = CapabilitiesLoader("/test/imports")

        assert isinstance(loader.imports_dir, Path)
        assert loader.imports_dir == Path("/test/imports")


class TestCapabilitiesLoaderReload:
    """Tests for CapabilitiesLoader.reload method."""

    def test_reload_gets_database_if_none(self, tmp_path):
        """Test that reload gets database if not provided."""
        mock_db = Mock()
        mock_db.clear_capabilities = Mock()

        with patch("olav.core.database.get_database", return_value=mock_db):
            loader = CapabilitiesLoader(tmp_path)
            result = loader.reload(dry_run=False)

            assert loader.db == mock_db
            mock_db.clear_capabilities.assert_called_once()

    def test_reload_clears_capabilities_when_not_dry_run(self, tmp_path):
        """Test that reload clears capabilities when not dry run."""
        mock_db = Mock()

        loader = CapabilitiesLoader(tmp_path, database=mock_db)
        loader.reload(dry_run=False)

        mock_db.clear_capabilities.assert_called_once()

    def test_reload_skips_clear_in_dry_run(self, tmp_path):
        """Test that reload skips clear in dry run mode."""
        mock_db = Mock()

        loader = CapabilitiesLoader(tmp_path, database=mock_db)
        loader.reload(dry_run=True)

        mock_db.clear_capabilities.assert_not_called()

    def test_reload_returns_counts(self, tmp_path):
        """Test that reload returns correct counts."""
        mock_db = Mock()

        loader = CapabilitiesLoader(tmp_path, database=mock_db)
        result = loader.reload()

        assert "commands" in result
        assert "apis" in result
        assert "total" in result
        assert result["total"] == result["commands"] + result["apis"]


class TestCapabilitiesLoaderLoadCommands:
    """Tests for CapabilitiesLoader._load_commands method."""

    def test_load_commands_no_directory(self, tmp_path):
        """Test loading when commands directory doesn't exist."""
        loader = CapabilitiesLoader(tmp_path, database=Mock())

        count = loader._load_commands(dry_run=False)

        assert count == 0

    def test_load_commands_skip_disabled_files(self, tmp_path):
        """Test that files starting with _ are skipped."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)

        # Create disabled file
        (commands_dir / "_disabled.txt").write_text("show run")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_commands(dry_run=False)

        assert count == 0
        mock_db.insert_capability.assert_not_called()

    def test_load_commands_parse_read_commands(self, tmp_path):
        """Test parsing read commands."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)

        (commands_dir / "cisco_ios.txt").write_text("show run\nshow ip int brief")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_commands(dry_run=False)

        assert count == 2
        assert mock_db.insert_capability.call_count == 2

        # Verify first call
        call1 = mock_db.insert_capability.call_args_list[0]
        assert call1.kwargs["cap_type"] == "command"
        assert call1.kwargs["platform"] == "cisco_ios"
        assert call1.kwargs["name"] == "show run"
        assert call1.kwargs["is_write"] is False

    def test_load_commands_parse_write_commands(self, tmp_path):
        """Test parsing write commands (starting with !)."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)

        (commands_dir / "cisco_ios.txt").write_text("!configure terminal\n!write memory")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_commands(dry_run=False)

        assert count == 2

        # Verify write flag is set
        for call in mock_db.insert_capability.call_args_list:
            assert call.kwargs["is_write"] is True
            assert not call.kwargs["name"].startswith("!")

    def test_load_commands_skip_comments(self, tmp_path):
        """Test that comments (starting with #) are skipped."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)

        (commands_dir / "cisco_ios.txt").write_text("# This is a comment\nshow run")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_commands(dry_run=False)

        assert count == 1

    def test_load_commands_skip_empty_lines(self, tmp_path):
        """Test that empty lines are skipped."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)

        (commands_dir / "cisco_ios.txt").write_text("\n\nshow run\n\n")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_commands(dry_run=False)

        assert count == 1

    def test_load_commands_dry_run(self, tmp_path):
        """Test dry run mode doesn't insert to database."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)

        (commands_dir / "cisco_ios.txt").write_text("show run")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_commands(dry_run=True)

        assert count == 1
        mock_db.insert_capability.assert_not_called()

    def test_load_commands_multiple_platforms(self, tmp_path):
        """Test loading commands from multiple platform files."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)

        (commands_dir / "cisco_ios.txt").write_text("show run")
        (commands_dir / "arista_eos.txt").write_text("show version")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_commands(dry_run=False)

        assert count == 2

        # Verify platforms
        platforms = [
            call.kwargs["platform"]
            for call in mock_db.insert_capability.call_args_list
        ]
        assert "cisco_ios" in platforms
        assert "arista_eos" in platforms


class TestCapabilitiesLoaderLoadApis:
    """Tests for CapabilitiesLoader._load_apis method."""

    def test_load_apis_no_directory(self, tmp_path):
        """Test loading when apis directory doesn't exist."""
        loader = CapabilitiesLoader(tmp_path, database=Mock())

        count = loader._load_apis(dry_run=False)

        assert count == 0

    def test_load_apis_skip_disabled_files(self, tmp_path):
        """Test that files starting with _ are skipped."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        # Create disabled file
        (apis_dir / "_disabled.yaml").write_text("")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_apis(dry_run=False)

        assert count == 0

    def test_load_apis_parse_yaml(self, tmp_path):
        """Test parsing YAML OpenAPI spec."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        spec = {
            "paths": {
                "/api/devices/": {
                    "get": {
                        "summary": "List devices",
                        "description": "Get all devices",
                    }
                }
            }
        }

        with open(apis_dir / "netbox.yaml", "w") as f:
            yaml.dump(spec, f)

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_apis(dry_run=False)

        assert count == 1
        mock_db.insert_capability.assert_called_once()

        # Verify call arguments
        call_kwargs = mock_db.insert_capability.call_args.kwargs
        assert call_kwargs["cap_type"] == "api"
        assert call_kwargs["platform"] == "netbox"
        assert call_kwargs["name"] == "/api/devices/"
        assert call_kwargs["method"] == "GET"

    def test_load_apis_write_flag_from_x_olav_write(self, tmp_path):
        """Test write flag from x-olav-write extension for GET method."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        spec = {
            "paths": {
                "/api/devices/": {
                    "get": {
                        "summary": "Get devices",
                        "x-olav-write": True,  # Override default for GET
                    }
                }
            }
        }

        with open(apis_dir / "netbox.yaml", "w") as f:
            yaml.dump(spec, f)

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        loader._load_apis(dry_run=False)

        # Verify write flag is True despite being GET
        call_kwargs = mock_db.insert_capability.call_args.kwargs
        assert call_kwargs["is_write"] is True

    def test_load_apis_default_write_for_non_get(self, tmp_path):
        """Test that non-GET methods default to write=True."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        spec = {
            "paths": {
                "/api/devices/": {
                    "delete": {
                        "summary": "Delete device",
                    }
                }
            }
        }

        with open(apis_dir / "netbox.yaml", "w") as f:
            yaml.dump(spec, f)

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        loader._load_apis(dry_run=False)

        call_kwargs = mock_db.insert_capability.call_args.kwargs
        assert call_kwargs["is_write"] is True

    def test_load_apis_invalid_yaml_continues(self, tmp_path):
        """Test that invalid YAML files are skipped gracefully."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        # Create invalid YAML
        (apis_dir / "invalid.yaml").write_text("invalid: yaml: content: [")

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_apis(dry_run=False)

        assert count == 0
        mock_db.insert_capability.assert_not_called()

    def test_load_apis_missing_paths(self, tmp_path):
        """Test that specs without 'paths' are skipped."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        spec = {"info": {"title": "API"}}

        with open(apis_dir / "invalid.yaml", "w") as f:
            yaml.dump(spec, f)

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_apis(dry_run=False)

        assert count == 0

    def test_load_apis_dry_run(self, tmp_path):
        """Test dry run mode doesn't insert to database."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        spec = {"paths": {"/api/devices/": {"get": {"summary": "List"}}}}

        with open(apis_dir / "netbox.yaml", "w") as f:
            yaml.dump(spec, f)

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_apis(dry_run=True)

        assert count == 1
        mock_db.insert_capability.assert_not_called()

    def test_load_apis_multiple_methods(self, tmp_path):
        """Test loading multiple HTTP methods for same path."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)

        spec = {
            "paths": {
                "/api/devices/{id}/": {
                    "get": {"summary": "Get device"},
                    "patch": {"summary": "Update device"},
                    "delete": {"summary": "Delete device"},
                }
            }
        }

        with open(apis_dir / "netbox.yaml", "w") as f:
            yaml.dump(spec, f)

        mock_db = Mock()
        loader = CapabilitiesLoader(tmp_path, database=mock_db)

        count = loader._load_apis(dry_run=False)

        assert count == 3

        methods = [call.kwargs["method"] for call in mock_db.insert_capability.call_args_list]
        assert "GET" in methods
        assert "PATCH" in methods
        assert "DELETE" in methods


class TestCapabilitiesLoaderValidate:
    """Tests for CapabilitiesLoader.validate method."""

    def test_validate_no_errors(self, tmp_path):
        """Test validation with valid files."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "cisco_ios.txt").write_text("show run")

        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)
        spec = {"paths": {"/api/": {"get": {"summary": "List"}}}}
        with open(apis_dir / "test.yaml", "w") as f:
            yaml.dump(spec, f)

        loader = CapabilitiesLoader(tmp_path)
        errors = loader.validate()

        assert errors == []

    def test_validate_empty_command(self, tmp_path):
        """Test validation detects empty commands."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "test.txt").write_text("!")

        loader = CapabilitiesLoader(tmp_path)
        errors = loader.validate()

        assert len(errors) > 0
        assert any("Empty command" in e for e in errors)

    def test_validate_invalid_yaml(self, tmp_path):
        """Test validation detects invalid YAML."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)
        (apis_dir / "invalid.yaml").write_text("invalid: yaml: [")

        loader = CapabilitiesLoader(tmp_path)
        errors = loader.validate()

        assert len(errors) > 0
        assert any("invalid.yaml" in e for e in errors)

    def test_validate_missing_paths(self, tmp_path):
        """Test validation detects missing 'paths' in OpenAPI spec."""
        apis_dir = tmp_path / "apis"
        apis_dir.mkdir(parents=True)
        with open(apis_dir / "invalid.yaml", "w") as f:
            yaml.dump({"info": "API"}, f)

        loader = CapabilitiesLoader(tmp_path)
        errors = loader.validate()

        assert len(errors) > 0
        assert any("Invalid OpenAPI spec" in e for e in errors)


# =============================================================================
# Test convenience functions
# =============================================================================


class TestReloadCapabilities:
    """Tests for reload_capabilities function."""

    def test_reload_capabilities_custom_dir(self, tmp_path):
        """Test reload with custom directory."""
        mock_loader = Mock()
        mock_loader.reload.return_value = {"commands": 1, "apis": 0, "total": 1}

        with patch("olav.tools.loader.CapabilitiesLoader", return_value=mock_loader):
            result = reload_capabilities(imports_dir=tmp_path)

            assert result["total"] == 1

    def test_reload_capabilities_dry_run(self, tmp_path):
        """Test reload with dry_run flag."""
        mock_loader = Mock()
        mock_loader.reload.return_value = {"commands": 5, "apis": 2, "total": 7}

        with patch("olav.tools.loader.CapabilitiesLoader", return_value=mock_loader):
            result = reload_capabilities(imports_dir=tmp_path, dry_run=True)

            # Verify dry_run was passed through
            mock_loader.reload.assert_called_once_with(dry_run=True)


class TestValidateCapabilities:
    """Tests for validate_capabilities function."""

    def test_validate_capabilities_custom_dir(self, tmp_path):
        """Test validate with custom directory."""
        mock_loader = Mock()
        mock_loader.validate.return_value = ["Error 1", "Error 2"]

        with patch("olav.tools.loader.CapabilitiesLoader", return_value=mock_loader):
            result = validate_capabilities(imports_dir=tmp_path)

            assert len(result) == 2
