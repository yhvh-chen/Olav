"""CLI Display Components - Banners and UI elements.

Provides:
- ASCII art banners (OLAV logo, snowman)
- Banner configuration system
- Rich-based UI rendering
"""

from enum import Enum
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None
    Text = None


# =============================================================================
# Banner Types Enum
# =============================================================================


class BannerType(Enum):
    """Available banner types."""

    OLAV = "olav"
    SNOWMAN = "snowman"
    DEEPAGENTS = "deepagents"
    MINIMAL = "minimal"
    NONE = "none"


# =============================================================================
# ASCII Art Banners
# =============================================================================

# Modern OLAV logo with gradient effect (ported from v0.5)
OLAV_LOGO = """[bold bright_cyan] ▄████▄ [/][bold blue]▓[/][bold white]  ██      [/][bold bright_green]  ▄████▄  [/][bold blue]▓[/][bold magenta]  ██    ██[/]
[bold bright_cyan]██▀  ▀██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ██▀  ▀██ [/][bold blue]▓[/][bold magenta]  ██    ██[/]
[bold bright_cyan]██    ██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ████████ [/][bold blue]▓[/][bold magenta]  ██    ██[/]
[bold bright_cyan]██▄  ▄██[/][bold blue]▓[/][bold white]  ██      [/][bold bright_green] ██    ██ [/][bold blue]▓[/][bold magenta]   ██  ██ [/]
[bold bright_cyan] ▀████▀ [/][bold blue]▓[/][bold white]  ████████[/][bold bright_green] ██    ██ [/][bold blue]▓[/][bold magenta]    ████  [/]
[bold blue] ▓▓▓▓▓▓ [/][bold blue] [/][bold grey39]  ▓▓▓▓▓▓▓▓[/][bold dark_green]  ▓▓    ▓▓ [/][bold blue] [/][bold purple]    ▓▓   [/]"""

# Modern snowman with cleaner aesthetic (ported from v0.5)
SNOWMAN_SMALL = """[cyan]   ✶   [/][bold white]▄▀▀▄[/][cyan]   ✶   [/]
[bold white]   .  ( [cyan]°[/] [cyan]°[/] )  .   [/]
[bold white]   . (  [orange1]>[/]  ) .    [/]
[bold white]  (   [red]~[/]   )      [/]
[bold white]  ▄▀     ▀▄     [/]
[dim white]   ❆   ❅   ❆   [/]"""

# Mini snowman
SNOWMAN_MINI = "[bold white]⛄[/] [cyan]❄[/] [white]❆[/] [cyan]❄[/]"

# Combined OLAV + Snowman banner
OLAV_SNOWMAN = f"""{OLAV_LOGO}

{SNOWMAN_SMALL}"""

# Minimal banner
OLAV_MINIMAL = "[bold cyan]OLAV[/] [bold white]v0.8[/] - [dim]Network Operations AI Assistant[/]"

# DeepAgents-style banner
DEEPAGENTS_ASCII = """[bold cyan]
  ╔════════════════════════════════════════════════════════════╗
  ║ [bold white]DeepAgents[/] [cyan]- Agentic AI Framework                   ║
  ║                                                            ║
  ║ [dim]Powered by LangGraph & LangChain                        ║
  ╚════════════════════════════════════════════════════════════╝
[/]"""


# =============================================================================
# Banner Display Functions
# =============================================================================


def get_banner(banner_type: BannerType = BannerType.SNOWMAN) -> str:
    """Get banner text for a given type.

    Args:
        banner_type: Type of banner to display

    Returns:
        Banner text string
    """
    if banner_type == BannerType.OLAV:
        return OLAV_LOGO
    elif banner_type == BannerType.SNOWMAN:
        return OLAV_SNOWMAN
    elif banner_type == BannerType.DEEPAGENTS:
        return DEEPAGENTS_ASCII
    elif banner_type == BannerType.MINIMAL:
        return OLAV_MINIMAL
    else:
        return ""


def display_banner(
    banner_type: BannerType = BannerType.SNOWMAN,
    console: Optional[Console] = None,
) -> None:
    """Display a banner to the console.

    Args:
        banner_type: Type of banner to display
        console: Rich console instance (creates new if None)
    """
    banner_text = get_banner(banner_type)

    if not banner_text:
        return

    if not RICH_AVAILABLE:
        # Fallback without rich
        print(banner_text)
        return

    if console is None:
        console = Console()

    # Parse and display rich markup
    text = Text.from_markup(banner_text)
    console.print(text)


def load_banner_from_config(settings_path: Path | None = None) -> BannerType:
    """Load banner type from settings configuration.

    Args:
        settings_path: Path to settings.json (default: .olav/settings.json)

    Returns:
        BannerType enum value
    """
    import json

    if settings_path is None:
        settings_path = Path(".olav/settings.json")

    if not settings_path.exists():
        return BannerType.SNOWMAN  # Default

    try:
        settings = json.loads(settings_path.read_text())
        banner_config = settings.get("cli", {}).get("banner", "snowman")

        # Map string to enum
        banner_map = {
            "olav": BannerType.OLAV,
            "snowman": BannerType.SNOWMAN,
            "deepagents": BannerType.DEEPAGENTS,
            "minimal": BannerType.MINIMAL,
            "none": BannerType.NONE,
        }

        return banner_map.get(banner_config.lower(), BannerType.SNOWMAN)
    except (json.JSONDecodeError, KeyError):
        return BannerType.SNOWMAN  # Default on error


# =============================================================================
# UI Helpers
# =============================================================================


def print_welcome(console: Optional[Console] = None) -> None:
    """Print welcome message with banner.

    Args:
        console: Rich console instance
    """
    if console is None:
        console = Console() if RICH_AVAILABLE else None

    # Load banner type from config
    banner_type = load_banner_from_config()

    # Display banner
    display_banner(banner_type, console)

    # Print welcome message
    if console:
        console.print(
            "\n[bold green]Welcome to OLAV v0.8[/] - [dim]Network Operations AI Assistant[/]"
        )
        console.print("[dim]Type /help for available commands[/]\n")
    else:
        print("\nWelcome to OLAV v0.8 - Network Operations AI Assistant")
        print("Type /help for available commands\n")


def print_error(message: str, console: Optional[Console] = None) -> None:
    """Print error message.

    Args:
        message: Error message to display
        console: Rich console instance
    """
    if console:
        console.print(f"[bold red]Error:[/] {message}")
    else:
        print(f"Error: {message}")


def print_success(message: str, console: Optional[Console] = None) -> None:
    """Print success message.

    Args:
        message: Success message to display
        console: Rich console instance
    """
    if console:
        console.print(f"[bold green]✓[/] {message}")
    else:
        print(f"✓ {message}")


def print_warning(message: str, console: Optional[Console] = None) -> None:
    """Print warning message.

    Args:
        message: Warning message to display
        console: Rich console instance
    """
    if console:
        console.print(f"[bold yellow]⚠[/] {message}")
    else:
        print(f"⚠ {message}")
