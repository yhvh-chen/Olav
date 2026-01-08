"""Input Parser - Parse and enhance user input.

Handles:
- File references (@file.txt)
- Shell command execution (!command)
- Multi-line input detection
"""

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def expand_file_references(text: str, base_dir: Path | None = None) -> str:
    """Expand @file references to file content.

    Args:
        text: Input text potentially containing @file.txt
        base_dir: Base directory for resolving relative paths (for testing)

    Returns:
        Text with file references expanded

    Example:
        "@config.txt" → "```text\\n<file content>\\n```"
    """
    pattern = r"@([\w./\\-]+)"

    def replace_ref(match):
        filepath = match.group(1)
        path = Path(filepath)

        # If base_dir is provided and path is relative, resolve from base_dir
        if base_dir is not None and not path.is_absolute():
            path = base_dir / path

        if path.exists() and path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
                # Determine format from extension
                suffix = path.suffix[1:] if path.suffix else "text"
                return f"\n```{suffix}\n{content}\n```\n"
            except Exception:
                # If file can't be read, expand reference inline
                try:
                    # Try reading without encoding
                    content = path.read_text()
                    suffix = path.suffix[1:] if path.suffix else "text"
                    return f"\n```{suffix}\n{content}\n```\n"
                except Exception:
                    # Keep reference if file can't be read
                    return match.group(0)
        else:
            # File doesn't exist, keep reference
            return match.group(0)

    return re.sub(pattern, replace_ref, text)


def parse_input(text: str) -> Tuple[str, bool, Optional[str]]:
    """Parse user input into components.

    Args:
        text: Raw user input

    Returns:
        Tuple of (processed_text, is_shell_command, shell_command)
        - processed_text: Text with expansions applied
        - is_shell_command: True if this is a shell command (!command)
        - shell_command: The shell command if is_shell_command, else None

    Examples:
        "ping 8.8.8.8" → ("ping 8.8.8.8", False, None)
        "!ping 8.8.8.8" → ("!ping 8.8.8.8", True, "ping 8.8.8.8")
        "@config.txt" → ("```text\\n<content>\\n```", False, None)
    """
    text = text.strip()

    # Check for shell command (!command)
    if text.startswith("!"):
        shell_cmd = text[1:].strip()
        return text, True, shell_cmd

    # Expand file references
    text = expand_file_references(text)

    return text, False, None


def execute_shell_command(command: str) -> Tuple[bool, str, str, int]:
    """Execute a shell command.

    Args:
        command: Shell command to execute

    Returns:
        Tuple of (success, stdout, stderr, return_code)

    Example:
        success, stdout, stderr, code = execute_shell_command("ls -la")
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )

        success = result.returncode == 0
        stdout = result.stdout
        stderr = result.stderr
        return_code = result.returncode

        return success, stdout, stderr, return_code

    except subprocess.TimeoutExpired:
        return False, "", "Command timed out after 30 seconds", -1
    except Exception as e:
        return False, "", str(e), -1


def detect_multiline(text: str) -> bool:
    """Check if input should be treated as multi-line.

    Multi-line mode is activated when:
    - Input contains newlines
    - Input ends with backslash
    - Input is a code block (triple backticks)

    Args:
        text: Input text

    Returns:
        True if should use multi-line mode
    """
    # Contains newlines
    if "\n" in text:
        return True

    # Ends with backslash (line continuation)
    if text.endswith("\\"):
        return True

    # Is a code block
    if "```" in text:
        return True

    return False


def strip_code_blocks(text: str) -> str:
    """Remove code block markdown wrappers if present.

    Args:
        text: Input text

    Returns:
        Text with ``` wrappers removed

    Example:
        "```python\\nprint('hello')\\n```" → "print('hello')"
    """
    # Remove leading/trailing code blocks
    text = text.strip()

    # Check for code block pattern
    if text.startswith("```"):
        # Find first newline after opening ```
        first_newline = text.find("\n")
        if first_newline > 0:
            # Find closing ```
            last_triple_backtick = text.rfind("```")
            if last_triple_backtick > first_newline:
                # Extract content between
                content = text[first_newline + 1:last_triple_backtick].strip()
                return content

    return text
