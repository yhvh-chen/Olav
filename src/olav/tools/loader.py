"""Capabilities loader for OLAV v0.8.

This module implements the 'olav reload' functionality that loads
CLI commands and API definitions from the imports/ directory into DuckDB.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from olav.core.database import OlavDatabase


class CommandFileFormat(BaseModel):
    """Format of command text files.

    Each line is a command. Lines starting with '#' are comments.
    Lines starting with '!' are write commands (require HITL).
    Wildcards (*) are supported for command matching.
    """

    lines: list[str]


class APIEndpoint(BaseModel):
    """OpenAPI endpoint definition."""

    path: str
    method: str
    summary: str | None = None
    is_write: bool = False
    parameters: dict[str, Any] | None = None


class CapabilitiesLoader:
    """Load capabilities from imports/ directory into DuckDB."""

    def __init__(self, imports_dir: Path, database: OlavDatabase | None = None) -> None:
        """Initialize loader.

        Args:
            imports_dir: Path to imports/ directory
            database: Optional database instance (uses default if not provided)
        """
        self.imports_dir = Path(imports_dir)
        self.db = database

    def reload(self, dry_run: bool = False) -> dict[str, int]:
        """Reload capabilities from imports/ directory.

        Args:
            dry_run: If True, only validate without loading

        Returns:
            Dictionary with counts: {"commands": N, "apis": M, "total": N+M}
        """
        if self.db is None:
            from olav.core.database import get_database

            self.db = get_database()

        if not dry_run:
            self.db.clear_capabilities()

        command_count = self._load_commands(dry_run)
        api_count = self._load_apis(dry_run)

        return {"commands": command_count, "apis": api_count, "total": command_count + api_count}

    def _load_commands(self, dry_run: bool) -> int:
        """Load CLI commands from imports/commands/*.txt.

        Args:
            dry_run: If True, only validate

        Returns:
            Number of commands loaded
        """
        commands_dir = self.imports_dir / "commands"
        if not commands_dir.exists():
            return 0

        count = 0

        for txt_file in commands_dir.glob("*.txt"):
            # Skip disabled files (starting with _)
            if txt_file.name.startswith("_"):
                continue

            platform = txt_file.stem  # cisco_ios.txt -> cisco_ios

            # Read and parse commands
            lines = txt_file.read_text(encoding="utf-8").strip().split("\n")

            for line in lines:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Check if it's a write command
                is_write = line.startswith("!")
                command = line[1:] if is_write else line

                # Remove leading/trailing whitespace
                command = command.strip()

                if not command:
                    continue

                if not dry_run:
                    self.db.insert_capability(
                        cap_type="command",
                        platform=platform,
                        name=command,
                        source_file=str(txt_file.relative_to(self.imports_dir)),
                        is_write=is_write,
                    )

                count += 1

        return count

    def _load_apis(self, dry_run: bool) -> int:
        """Load API definitions from imports/apis/*.yaml.

        Args:
            dry_run: If True, only validate

        Returns:
            Number of API endpoints loaded
        """
        apis_dir = self.imports_dir / "apis"
        if not apis_dir.exists():
            return 0

        count = 0

        for yaml_file in apis_dir.glob("*.yaml"):
            # Skip disabled files (starting with _)
            if yaml_file.name.startswith("_"):
                continue

            platform = yaml_file.stem  # netbox.yaml -> netbox

            try:
                spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            except yaml.YAMLError as e:
                print(f"Error parsing {yaml_file}: {e}")
                continue

            # Validate OpenAPI format
            if not isinstance(spec, dict) or "paths" not in spec:
                print(f"Invalid OpenAPI spec in {yaml_file}: missing 'paths'")
                continue

            # Extract endpoints from paths
            for path, path_spec in spec["paths"].items():
                if not isinstance(path_spec, dict):
                    continue

                for method, method_spec in path_spec.items():
                    if method.lower() not in ["get", "post", "put", "patch", "delete"]:
                        continue

                    if not isinstance(method_spec, dict):
                        continue

                    # Check for OLAV-specific write flag
                    is_write = method_spec.get("x-olav-write", False)

                    # Default to write=True for non-GET methods
                    if not is_write and method.lower() in ["post", "put", "patch", "delete"]:
                        is_write = True

                    summary = method_spec.get("summary", method_spec.get("description"))

                    if not dry_run:
                        self.db.insert_capability(
                            cap_type="api",
                            platform=platform,
                            name=path,
                            source_file=str(yaml_file.relative_to(self.imports_dir)),
                            method=method.upper(),
                            description=summary,
                            is_write=is_write,
                        )

                    count += 1

        return count

    def validate(self) -> list[str]:
        """Validate all files in imports/ directory.

        Returns:
            List of error messages (empty if all valid)
        """
        errors = []

        # Validate command files
        commands_dir = self.imports_dir / "commands"
        if commands_dir.exists():
            for txt_file in commands_dir.glob("*.txt"):
                if txt_file.name.startswith("_"):
                    continue

                try:
                    lines = txt_file.read_text(encoding="utf-8").split("\n")
                    for i, line in enumerate(lines, 1):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Remove write marker
                            if line.startswith("!"):
                                line = line[1:]

                            if not line.strip():
                                errors.append(f"{txt_file}:{i}: Empty command")

                except Exception as e:
                    errors.append(f"{txt_file}: {e}")

        # Validate API files
        apis_dir = self.imports_dir / "apis"
        if apis_dir.exists():
            for yaml_file in apis_dir.glob("*.yaml"):
                if yaml_file.name.startswith("_"):
                    continue

                try:
                    spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                    if not isinstance(spec, dict) or "paths" not in spec:
                        errors.append(f"{yaml_file}: Invalid OpenAPI spec")

                except yaml.YAMLError as e:
                    errors.append(f"{yaml_file}: {e}")

        return errors


def reload_capabilities(
    imports_dir: str | Path = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Convenience function to reload capabilities.

    Args:
        imports_dir: Path to imports/ directory (defaults to agent_dir/imports)
        dry_run: If True, only validate without loading

    Returns:
        Dictionary with counts
    """
    if imports_dir is None:
        from config.settings import settings
        imports_dir = str(Path(settings.agent_dir) / "imports")

    loader = CapabilitiesLoader(Path(imports_dir))
    return loader.reload(dry_run=dry_run)


def validate_capabilities(imports_dir: str | Path = None) -> list[str]:
    """Convenience function to validate capabilities.

    Args:
        imports_dir: Path to imports/ directory (defaults to agent_dir/imports)

    Returns:
        List of error messages
    """
    if imports_dir is None:
        from config.settings import settings
        imports_dir = str(Path(settings.agent_dir) / "imports")

    loader = CapabilitiesLoader(Path(imports_dir))
    return loader.validate()
