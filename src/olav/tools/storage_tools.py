"""Storage Tools - File read/write capabilities for OLAV agent.

This module provides safe file storage operations for:
- Device configurations (running-config, startup-config)
- Show tech outputs
- Logs and troubleshooting data
- Knowledge base updates

All write operations require HITL approval for safety.

Phase 7: Agentic Report Embedding - automatically embeds reports written to data/reports/
"""

import logging
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from config.settings import settings

logger = logging.getLogger(__name__)


def _get_allowed_dirs() -> list[str]:
    """Get allowed directories based on agent_dir configuration.

    Returns:
        List of allowed directory paths
    """
    agent_dir = settings.agent_dir
    return [
        "data/exports",  # Exported device data (configs, MAC tables, etc.)
        "data/reports",  # Analysis reports
        "data/logs",  # Application and Nornir logs
        f"{agent_dir}/knowledge/solutions",  # Troubleshooting solutions
        f"{agent_dir}/scratch",  # Temporary files
    ]


def _get_allowed_read_dirs() -> list[str]:
    """Get allowed read directories based on agent_dir configuration.

    Returns:
        List of allowed read directory paths
    """
    agent_dir = settings.agent_dir
    return [
        f"{agent_dir}/",  # All agent content
    ]


# Allowed directories for file operations (lazy evaluation)
ALLOWED_WRITE_DIRS = _get_allowed_dirs()
ALLOWED_READ_DIRS = _get_allowed_read_dirs()


def _is_path_allowed(filepath: str, allowed_dirs: list[str]) -> bool:
    """Check if a path is within allowed directories.

    Args:
        filepath: Path to check
        allowed_dirs: List of allowed directory prefixes

    Returns:
        True if path is allowed, False otherwise
    """
    # Normalize path
    path = Path(filepath)

    # Convert to relative path if absolute
    try:
        path = path.relative_to(Path.cwd())
    except ValueError:
        pass

    path_str = str(path).replace("\\", "/")

    for allowed in allowed_dirs:
        if path_str.startswith(allowed):
            return True

    return False


def _auto_embed_report(filepath: str) -> str:
    """Auto-embed markdown reports to knowledge base (Phase 7).

    When a report is written to data/reports/*.md, automatically embed it
    to the DuckDB knowledge vector store for retrieval.

    Args:
        filepath: Path to the report file that was just written

    Returns:
        Status message (success or failure)
    """
    try:
        path = Path(filepath)

        # Only auto-embed markdown reports in data/reports/
        if not (path.suffix.lower() == ".md" and "data/reports" in str(path)):
            return ""  # Silent skip for non-markdown files

        # Lazy import to avoid circular dependencies
        from olav.tools.knowledge_embedder import KnowledgeEmbedder

        embedder = KnowledgeEmbedder()

        # Embed as report source (source_id=3 for reports)
        count = embedder.embed_file(path, source_id=3, platform="report")

        if count > 0:
            logger.info(f"✅ Auto-embedded report {path.name}: {count} chunks")
            return f"✅ Auto-embedded {path.name} to knowledge base ({count} chunks)"
        else:
            logger.debug(f"Report {path.name} already indexed or empty")
            return ""  # Silent skip if already indexed

    except Exception as e:
        logger.warning(f"Auto-embedding failed for {filepath}: {e}")
        return f"⚠️ Auto-embedding skipped: {e}"


@tool
def write_file(
    filepath: str,
    content: str,
    create_dirs: bool = True,
) -> str:
    """Write content to a file in the OLAV knowledge base.

    This tool saves data to the local filesystem. Allowed directories:
    - data/exports/ - Exported device data (configs, MAC tables, ARP, etc.)
    - data/reports/ - Analysis reports (auto-embedded to KB)
    - data/logs/ - Application and Nornir logs
    - agent_dir/knowledge/solutions/ - Troubleshooting solutions
    - agent_dir/scratch/ - Temporary files

    IMPORTANT: This operation requires HITL approval.

    Phase 7 Enhancement: Markdown reports (.md) in data/reports/ are automatically
    embedded to the knowledge vector store for agentic retrieval.

    Args:
        filepath: Path to write (relative to project root, e.g., "data/exports/R1-config.txt")
        content: Content to write
        create_dirs: Whether to create parent directories if they don't exist

    Returns:
        Success message with filepath, or error message

    Examples:
        path = "data/exports/R1-running-config.txt"
        write_file(path, config_output)
    """
    # Validate path
    if not _is_path_allowed(filepath, ALLOWED_WRITE_DIRS):
        msg = (
            f"❌ Error: Path '{filepath}' is not in allowed directories. "
            f"Allowed: {ALLOWED_WRITE_DIRS}"
        )
        return msg

    try:
        path = Path(filepath)

        # Create parent directories if needed
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        path.write_text(content, encoding="utf-8")

        # Get file size
        size = path.stat().st_size
        result = f"✅ File saved: {filepath} ({size} bytes)"

        # Phase 7: Auto-embed markdown reports to knowledge base
        embed_status = _auto_embed_report(filepath)
        if embed_status:
            result += f"\n{embed_status}"

        return result

    except Exception as e:
        return f"❌ Error writing file: {str(e)}"


@tool
def read_file(
    filepath: str,
) -> str:
    """Read content from a file in the OLAV knowledge base.

    This tool reads data from the local filesystem. Can read from any agent_dir/ directory.

    Args:
        filepath: Path to read (relative to project root)

    Returns:
        File content, or error message

    Examples:
        read_file("data/exports/R1-running-config.txt")
        read_file(f"{settings.agent_dir}/skills/quick-query.md")
    """
    # Validate path
    if not _is_path_allowed(filepath, ALLOWED_READ_DIRS):
        return f"❌ Error: Path '{filepath}' is not in allowed directories."

    try:
        path = Path(filepath)

        if not path.exists():
            return f"❌ Error: File not found: {filepath}"

        content = path.read_text(encoding="utf-8")
        return content

    except Exception as e:
        return f"❌ Error reading file: {str(e)}"


@tool
def save_device_config(
    device: str,
    config_type: str,
    content: str,
) -> str:
    """Save a device configuration to the knowledge base.

    This is a convenience tool for saving device configs with proper naming.

    Args:
        device: Device name (e.g., "R1", "SW1")
        config_type: Type of config ("running", "startup", "backup")
        content: Configuration content

    Returns:
        Success message with filepath

    Example:
        save_device_config("R1", "running", show_run_output)
    """
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{device}-{config_type}-config-{timestamp}.txt"
    filepath = str(Path(settings.agent_dir) / "data" / "configs" / filename)

    # Add metadata header
    header = f"""! Device: {device}
! Config Type: {config_type}
! Saved: {datetime.now().isoformat()}
! Source: OLAV automated backup
!
"""
    full_content = header + content

    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(full_content, encoding="utf-8")

        size = path.stat().st_size
        return f"✅ Config saved: {filepath} ({size} bytes)"

    except Exception as e:
        return f"❌ Error saving config: {str(e)}"


@tool
def save_tech_support(
    device: str,
    content: str,
) -> str:
    """Save show tech-support output to the knowledge base.

    Tech-support outputs are large and useful for TAC cases.

    Args:
        device: Device name
        content: Show tech-support output

    Returns:
        Success message with filepath
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{device}-tech-support-{timestamp}.txt"
    filepath = str(Path(settings.agent_dir) / "data" / "reports" / filename)

    header = f"""! Device: {device}
! Type: show tech-support
! Captured: {datetime.now().isoformat()}
! Source: OLAV
!
"""
    full_content = header + content

    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(full_content, encoding="utf-8")

        size = path.stat().st_size
        size_kb = size / 1024
        result = f"✅ Tech-support saved: {filepath} ({size_kb:.1f} KB)"

        # Note: Tech-support files are .txt, so auto-embedding doesn't apply
        # (Phase 7 auto-embedding is for .md files only)

        return result

    except Exception as e:
        return f"❌ Error saving tech-support: {str(e)}"


@tool
def list_saved_files(
    directory: str | None = None,
    pattern: str = "*",
) -> str:
    """List files saved in the OLAV knowledge base.

    Args:
        directory: Directory to list (must be under agent_dir/)
        pattern: Glob pattern to filter files (e.g., "*.txt", "R1-*")

    Returns:
        List of files with sizes
    """
    if directory is None:
        directory = str(Path(settings.agent_dir) / "knowledge")

    if not _is_path_allowed(directory, ALLOWED_READ_DIRS):
        return f"❌ Error: Directory '{directory}' is not accessible."

    try:
        path = Path(directory)

        if not path.exists():
            return f"📁 Directory '{directory}' does not exist yet."

        files = list(path.rglob(pattern))

        if not files:
            return f"📁 No files matching '{pattern}' in {directory}"

        result = [f"📁 Files in {directory}:"]
        for f in sorted(files):
            if f.is_file():
                size = f.stat().st_size
                rel_path = f.relative_to(path)
                if size > 1024:
                    result.append(f"  - {rel_path} ({size / 1024:.1f} KB)")
                else:
                    result.append(f"  - {rel_path} ({size} bytes)")

        return "\n".join(result)

    except Exception as e:
        return f"❌ Error listing files: {str(e)}"
