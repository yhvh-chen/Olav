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


def display_banner(banner_text: str, console: Console | None = None) -> None:
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
            "\n[bold green]Welcome to OLAV v0.8[/] - [dim]Network Operations AI Assistant[/]"
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


class StreamingDisplay:
    """Hierarchical streaming output handler for agent execution.

    Manages three levels of output:
    1. Thinking process (LLM reasoning) - shown in dim/dark color
    2. Tool calls (network execution) - shown in highlight Panel
    3. Final results (formatted output) - shown in standard color

    Supports both verbose mode (all output) and compact mode (tools + results only).
    """

    def __init__(
        self,
        console: Console | None = None,
        verbose: bool = False,
        show_spinner: bool = True,
    ) -> None:
        """Initialize streaming display.

        Args:
            console: Rich Console instance (creates new if None)
            verbose: Show full thinking process if True
            show_spinner: Show spinner during processing if True
        """
        if not RICH_AVAILABLE:
            raise ImportError("Rich library required for StreamingDisplay")

        # Create console with force_terminal and no_color for better streaming
        self.console = console or Console(force_terminal=True, force_interactive=False)
        self.verbose = verbose
        self.show_spinner = show_spinner
        self._current_spinner = None

    def show_thinking(self, text: str, end: str = "") -> None:
        """Display LLM thinking/reasoning (streaming tokens).

        Args:
            text: Thinking content to display
            end: End character (empty string for delta, newline for finalized)
        """
        if not self.verbose:
            return

        # Stream tokens in normal color (not dim)
        self.console.print(text, end=end, highlight=False)
        # Force flush to show streaming tokens immediately
        self.console.file.flush()

    def show_tool_compact(self, tool_name: str, detail: str | None = None) -> None:
        """Display tool call in compact single-line format.

        Args:
            tool_name: Name of the tool being called
            detail: Optional detail (device, query, etc.)
        """
        if detail:
            self.console.print(f"[dim]  → {tool_name}[/dim] [cyan]{detail}[/cyan]")
        else:
            self.console.print(f"[dim]  → {tool_name}...[/dim]")
        self.console.file.flush()

    def show_tool_call(
        self,
        tool_name: str,
        device: str | None = None,
        command: str | None = None,
        status: str = "executing",
        compact: bool = False,
    ) -> None:
        """Display tool call in highlighted Panel format.

        Args:
            tool_name: Name of the tool being called
            device: Target device (optional)
            command: Command being executed (optional)
            status: Status string ('executing', 'completed', 'failed')
            compact: If True, use compact single-line display
        """
        # Use compact display for less important tools
        if compact:
            detail = device or command or None
            self.show_tool_compact(tool_name, detail)
            return

        from rich.panel import Panel

        # Build title with status indicator
        status_icons = {
            "executing": "⏳",
            "completed": "✅",
            "failed": "❌",
        }
        icon = status_icons.get(status, "🔧")

        title = f"{icon} {tool_name}"
        if device:
            title += f" | {device}"

        # Build content
        content = ""
        if command:
            content = f"Command: `{command}`"

        # Display as panel
        panel = Panel(
            content or "Processing...",
            title=title,
            border_style="cyan" if status == "executing" else "green",
            expand=False,
        )
        self.console.print(panel)

    def show_result(self, text: str, end: str = "", markdown: bool = False) -> None:
        """Display final result in standard format.

        Args:
            text: Result content to display
            end: End character (empty string for delta, newline for finalized)
            markdown: If True, render text as Markdown with syntax highlighting
        """
        if markdown and text.strip():
            from rich.markdown import Markdown

            md = Markdown(text)
            self.console.print(md)
        else:
            self.console.print(text, end=end, highlight=False)
        # Force flush to show streaming tokens immediately
        self.console.file.flush()

    def show_processing_status(self, message: str = "Processing...") -> None:
        """Show processing status indicator.

        Args:
            message: Status message to display
        """
        if not self.show_spinner:
            self.console.print(f"🔍 {message}")
            return

        # Use rich status for animated feedback
        from rich.live import Live
        from rich.spinner import Spinner

        spinner = Spinner("dots", text=f"[bold green]{message}[/bold green]")
        self._current_spinner = Live(spinner, refresh_per_second=4)
        self._current_spinner.start()

    def stop_processing_status(self) -> None:
        """Stop and clear the processing status indicator."""
        if self._current_spinner:
            self._current_spinner.stop()
            self._current_spinner = None

    def show_error(self, message: str) -> None:
        """Display error message.

        Args:
            message: Error message to display
        """
        self.console.print(f"[bold red]❌ Error:[/] {message}")
