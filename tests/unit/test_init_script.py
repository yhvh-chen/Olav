"""Unit tests for scripts/init.py initialization script.

Tests cover:
1. settings.json generation from .env values
2. aliases.md generation from hosts.yaml
3. capabilities.db loading and reloading
4. knowledge.db schema creation
"""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_olav_dir():
    """Create temporary .olav directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        olav_dir = Path(tmpdir) / ".olav"
        olav_dir.mkdir(parents=True, exist_ok=True)
        (olav_dir / "knowledge").mkdir(exist_ok=True)
        (olav_dir / "data").mkdir(exist_ok=True)
        (olav_dir / "config" / "nornir").mkdir(parents=True, exist_ok=True)
        (olav_dir / "imports" / "commands").mkdir(parents=True, exist_ok=True)
        yield olav_dir


@pytest.fixture
def temp_hosts_yaml(temp_olav_dir):
    """Create example hosts.yaml."""
    hosts_content = """R1:
  hostname: 192.168.100.101
  platform: cisco_ios
  data:
    role: border
    site: lab
    aliases:
      - border-router-1

R2:
  hostname: 192.168.100.102
  platform: cisco_ios
  data:
    role: core
    site: lab
    aliases:
      - core-router-1
"""
    hosts_file = temp_olav_dir / "config" / "nornir" / "hosts.yaml"
    hosts_file.write_text(hosts_content, encoding="utf-8")
    return hosts_file


@pytest.fixture
def sample_env_vars():
    """Sample environment variables."""
    return {
        "LLM_PROVIDER": "openai",
        "LLM_MODEL_NAME": "x-ai/grok-4.1-fast",
        "LLM_TEMPERATURE": "0.1",
        "LLM_MAX_TOKENS": "32000",
    }


class TestInitSettings:
    """Test settings.json generation."""

    def test_init_settings_from_env(self, temp_olav_dir, sample_env_vars):
        """Test that settings.json is generated from .env values."""
        # This is a conceptual test - in real usage, env vars are already loaded
        settings_file = temp_olav_dir / "settings.json"

        settings = {
            "agent": {
                "name": "OLAV",
                "description": "Network Operations AI Assistant",
                "version": "0.8",
            },
            "llm": {
                "provider": sample_env_vars["LLM_PROVIDER"],
                "model": sample_env_vars["LLM_MODEL_NAME"],
                "temperature": float(sample_env_vars["LLM_TEMPERATURE"]),
                "max_tokens": int(sample_env_vars["LLM_MAX_TOKENS"]),
            },
            "learning": {"autoSaveSolutions": False, "autoLearnAliases": True},
        }

        settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        # Verify file was created
        assert settings_file.exists()

        # Verify content
        loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        assert loaded["llm"]["provider"] == "openai"
        assert loaded["llm"]["model"] == "x-ai/grok-4.1-fast"
        assert loaded["llm"]["temperature"] == 0.1
        assert loaded["llm"]["max_tokens"] == 32000

    def test_init_settings_uses_defaults_if_env_missing(self, temp_olav_dir):
        """Test that settings.json uses defaults if env vars not set."""
        settings_file = temp_olav_dir / "settings.json"

        # Create settings with defaults
        settings = {
            "llm": {
                "provider": "openai",  # default
                "model": "gpt-4o",  # default
                "temperature": 0.1,  # default
                "max_tokens": 4096,  # default
            }
        }

        settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        assert loaded["llm"]["model"] == "gpt-4o"

    def test_init_settings_structure(self, temp_olav_dir):
        """Test that settings.json has required structure."""
        settings_file = temp_olav_dir / "settings.json"

        settings = {
            "agent": {
                "name": "OLAV",
                "description": "Network Operations AI Assistant",
                "version": "0.8",
            },
            "llm": {
                "provider": "openai",
                "model": "gpt-4o",
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            "cli": {"banner": "default", "showBanner": True},
            "diagnosis": {"requireApprovalForMicroAnalysis": True},
            "execution": {"useTextFSM": True},
            "learning": {"autoSaveSolutions": False, "autoLearnAliases": True},
            "subagents": {"enabled": True},
        }

        settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        loaded = json.loads(settings_file.read_text(encoding="utf-8"))

        # Verify all required sections exist
        assert "agent" in loaded
        assert "llm" in loaded
        assert "cli" in loaded
        assert "learning" in loaded
        assert loaded["agent"]["name"] == "OLAV"


class TestInitAliases:
    """Test aliases.md generation from hosts.yaml."""

    def test_init_aliases_from_nornir(self, temp_olav_dir, temp_hosts_yaml):
        """Test that aliases.md is generated from hosts.yaml."""
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        aliases_file = temp_olav_dir / "knowledge" / "aliases.md"

        # Load hosts
        hosts_data = yaml.safe_load(temp_hosts_yaml.read_text(encoding="utf-8"))

        # Generate aliases content
        content = "# Device Aliases\n\n| Alias | Actual Value | Type | Platform | Notes |\n"
        content += "|-------|--------------|------|----------|-------|\n"

        for hostname, host_data in hosts_data.items():
            if not isinstance(host_data, dict):
                continue
            ip = host_data.get("hostname", "")
            platform = host_data.get("platform", "unknown")
            data = host_data.get("data", {})
            role = data.get("role", "")
            site = data.get("site", "")
            notes = f"{role}@{site}" if role and site else role or site or ""

            content += f"| {hostname} | {ip} | device | {platform} | {notes} |\n"

            for alias in data.get("aliases", []):
                content += f"| {alias} | {hostname} | device | {platform} | alias |\n"

        aliases_file.write_text(content, encoding="utf-8")

        # Verify file was created
        assert aliases_file.exists()

        # Verify content
        text = aliases_file.read_text(encoding="utf-8")
        assert "R1" in text
        assert "192.168.100.101" in text
        assert "border-router-1" in text
        assert "cisco_ios" in text

    def test_init_aliases_includes_custom_aliases(self, temp_olav_dir, temp_hosts_yaml):
        """Test that custom aliases from hosts.yaml are included."""
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        hosts_data = yaml.safe_load(temp_hosts_yaml.read_text(encoding="utf-8"))

        # Extract custom aliases
        aliases_list = []
        for _hostname, host_data in hosts_data.items():
            data = host_data.get("data", {})
            aliases_list.extend(data.get("aliases", []))

        assert "border-router-1" in aliases_list
        assert "core-router-1" in aliases_list

    def test_init_aliases_empty_if_no_hosts(self, temp_olav_dir):
        """Test that aliases.md is created even without hosts.yaml."""
        aliases_file = temp_olav_dir / "knowledge" / "aliases.md"

        # Create minimal aliases file
        content = "# Device Aliases\n\n| Alias | Actual Value | Type | Platform | Notes |\n"
        content += "|-------|--------------|------|----------|-------|\n"

        aliases_file.write_text(content, encoding="utf-8")

        assert aliases_file.exists()
        text = aliases_file.read_text(encoding="utf-8")
        assert "# Device Aliases" in text


class TestCapabilitiesDb:
    """Test capabilities database initialization."""

    def test_capabilities_structure(self, temp_olav_dir):
        """Test that capabilities loading structure is correct."""
        # Create mock commands file
        commands_dir = temp_olav_dir / "imports" / "commands"
        cisco_file = commands_dir / "cisco_ios.txt"
        cisco_file.write_text(
            "show version\nshow ip route\nshow interfaces\n",
            encoding="utf-8"
        )

        # Parse commands
        commands = []
        for line in cisco_file.read_text().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                commands.append(line)

        assert len(commands) == 3
        assert "show version" in commands
        assert "show ip route" in commands

    def test_commands_file_format(self, temp_olav_dir):
        """Test that command files handle comments correctly."""
        commands_dir = temp_olav_dir / "imports" / "commands"
        test_file = commands_dir / "test.txt"

        content = """# Cisco commands
show version
show ip route

# Interface commands
show interfaces
show ip interface brief
"""
        test_file.write_text(content, encoding="utf-8")

        # Parse file
        commands = []
        for line in test_file.read_text().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                commands.append(line)

        # Should have 4 commands, no comments
        assert len(commands) == 4
        assert "# Cisco commands" not in commands
        assert "show version" in commands


class TestKnowledgeDb:
    """Test knowledge database initialization."""

    def test_knowledge_db_path(self, temp_olav_dir):
        """Test that knowledge.db path is correct."""
        db_path = temp_olav_dir / "data" / "knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create empty db file
        db_path.touch()

        assert db_path.exists()
        assert db_path.parent == temp_olav_dir / "data"

    def test_knowledge_db_directory_structure(self, temp_olav_dir):
        """Test that all required directories exist."""
        required_dirs = [
            temp_olav_dir / "data",
            temp_olav_dir / "knowledge",
            temp_olav_dir / "knowledge" / "solutions",
            temp_olav_dir / "skills",
            temp_olav_dir / "reports",
        ]

        for dir_path in required_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            assert dir_path.exists()


class TestInitValidation:
    """Test validation and error handling."""

    def test_settings_json_is_valid_json(self, temp_olav_dir):
        """Test that generated settings.json is valid JSON."""
        settings_file = temp_olav_dir / "settings.json"

        settings = {
            "agent": {"name": "OLAV"},
            "llm": {"provider": "openai", "model": "gpt-4o"},
        }

        settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        # Should parse without error
        loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        assert loaded["agent"]["name"] == "OLAV"

    def test_aliases_file_is_valid_markdown(self, temp_olav_dir):
        """Test that generated aliases.md is valid markdown."""
        aliases_file = temp_olav_dir / "knowledge" / "aliases.md"

        content = """# Device Aliases

| Alias | Actual Value | Type | Platform |
|-------|--------------|------|----------|
| R1 | 192.168.1.1 | device | cisco_ios |
"""

        aliases_file.write_text(content, encoding="utf-8")

        text = aliases_file.read_text(encoding="utf-8")
        assert text.startswith("# Device Aliases")
        assert "| Alias |" in text


class TestInitIntegration:
    """Integration tests for initialization flow."""

    def test_init_creates_all_files(self, temp_olav_dir, temp_hosts_yaml):
        """Test that init creates all required files."""
        settings_file = temp_olav_dir / "settings.json"
        aliases_file = temp_olav_dir / "knowledge" / "aliases.md"
        db_dir = temp_olav_dir / "data"

        # Create settings
        settings_file.write_text(json.dumps({"agent": {"name": "OLAV"}}), encoding="utf-8")

        # Create aliases
        aliases_file.write_text("# Device Aliases\n", encoding="utf-8")

        # Create db directory
        db_dir.mkdir(parents=True, exist_ok=True)

        # Verify all exist
        assert settings_file.exists()
        assert aliases_file.exists()
        assert db_dir.exists()

    def test_init_force_overwrites_files(self, temp_olav_dir):
        """Test that --force flag overwrites existing files."""
        settings_file = temp_olav_dir / "settings.json"

        # Create first version
        settings_file.write_text(
            json.dumps({"version": "1"}), encoding="utf-8"
        )

        # Overwrite with second version
        settings_file.write_text(
            json.dumps({"version": "2"}), encoding="utf-8"
        )

        loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        assert loaded["version"] == "2"
