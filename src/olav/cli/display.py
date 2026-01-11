"""CLI Display Components - Banners and UI elements.

Provides:
- Banner configuration system
- Rich-based UI rendering
"""


try:
    from rich.console import Console
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None
    Text = None


def get_banner(banner_name: str = "default") -> str:
    """Get banner text by name.

    Args:
        banner_name: Name of the banner from config.banners

    Returns:
        Banner text string
    """
    try:
        from config.banners import get_banner_text

        return get_banner_text(banner_name)
    except (ImportError, KeyError):
        # Fallback if config not available
        return ""


def load_banner_from_config(settings_path: str | None = None) -> str:
    """Load banner text from settings configuration.

    Args:
        settings_path: Path to settings.json (default: .olav/settings.json)

    Returns:
        Banner text string
    """
    import json
    from pathlib import Path

    if settings_path is None:
        from config.settings import settings as cfg

        settings_path = Path(cfg.agent_dir) / "settings.json"
    else:
        settings_path = Path(settings_path)

    if not settings_path.exists():
        return get_banner("default")

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        show_banner = settings.get("cli", {}).get("showBanner", True)

        if not show_banner:
            return ""

        banner_name = settings.get("cli", {}).get("banner", "default")
        return get_banner(banner_name)

    except (json.JSONDecodeError, KeyError):
        return get_banner("default")


def display_banner(
    banner_text: str, console: Console | None = None
) -> None:
    """Display a banner to the console.

    Args:
        banner_text: Banner text to display (supports Rich markup)
        console: Rich console instance (creates new if None)
    """
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


def print_welcome(console: Console | None = None) -> None:
    """Print welcome message with banner.

    Args:
        console: Rich console instance
    """
    if console is None:
        console = Console() if RICH_AVAILABLE else None

    # Load and display banner
    banner_text = load_banner_from_config()
    if banner_text:
        display_banner(banner_text, console)

    # Print welcome message
    if console:
        console.print(
            "\n[bold green]Welcome to OLAV v0.8[/] - "
            "[dim]Network Operations AI Assistant[/]"
        )
        console.print("[dim]Type /help for available commands[/]\n")
    else:
        print("\nWelcome to OLAV v0.8 - Network Operations AI Assistant")
        print("Type /help for available commands\n")


def print_error(message: str, console: Console | None = None) -> None:
    """Print error message.

    Args:
        message: Error message to display
        console: Rich console instance
    """
    if console:
        console.print(f"[bold red]Error:[/] {message}")
    else:
        print(f"Error: {message}")


def print_success(message: str, console: Console | None = None) -> None:
    """Print success message.

    Args:
        message: Success message to display
        console: Rich console instance
    """
    if console:
        console.print(f"[bold green]✓[/] {message}")
    else:
        print(f"✓ {message}")
