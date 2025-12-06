"""OLAV CLI REPL - Interactive Session with prompt_toolkit.

Features:
- History with fuzzy search
- Auto-completion for commands and device names
- Multi-line input support
- Syntax highlighting
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter, merge_completers
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console

if TYPE_CHECKING:
    from olav.cli.thin_client import OlavThinClient

logger = logging.getLogger(__name__)

# ============================================
# Completion & Style
# ============================================
SLASH_COMMANDS = [
    "/h", "/help",      # Help
    "/q", "/exit", "/quit",  # Exit
    "/s",              # Standard mode
    "/e",              # Expert mode
    "/c", "/clear",    # Clear screen
    "/his", "/history", # History
    "/info",           # Session info
]

MODE_OPTIONS = ["standard", "expert"]

EXAMPLE_QUERIES = [
    "check R1 BGP status",
    "show all device interfaces",
    "analyze OSPF neighbors",
    "display routing table",
    "audit border router config",
]

# Static command completer
command_completer = WordCompleter(
    SLASH_COMMANDS + MODE_OPTIONS + EXAMPLE_QUERIES,
    ignore_case=True,
    sentence=True,
)


class DynamicDeviceCompleter(Completer):
    """Dynamic completer that fetches device names from API.

    Caches device names with a TTL of 5 minutes.
    Falls back to cached values if API is unavailable.
    """

    def __init__(self, client: "OlavThinClient"):
        self.client = client
        self._cache: list[str] = []
        self._cache_time: float = 0
        self._cache_ttl: float = 300  # 5 minutes
        self._fetch_lock = asyncio.Lock()
        self._fetching = False

    def _should_refresh(self) -> bool:
        """Check if cache should be refreshed."""
        import time
        return (time.time() - self._cache_time) > self._cache_ttl

    async def _fetch_devices(self) -> list[str]:
        """Fetch device names from API."""
        async with self._fetch_lock:
            if not self._should_refresh() and self._cache:
                return self._cache

            try:
                devices = await self.client.get_device_names()
                if devices:
                    import time
                    self._cache = devices
                    self._cache_time = time.time()
                    logger.debug(f"Fetched {len(devices)} devices for autocomplete")
                else:
                    # Empty list or API not available - update cache time to avoid retry spam
                    import time
                    self._cache_time = time.time()
            except Exception:
                # Silently ignore - autocomplete is optional
                import time
                self._cache_time = time.time()  # Avoid retry spam

            return self._cache

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        """Get completions for the current document.

        This method is synchronous, so we use cached values.
        Background fetch is triggered for next completion.
        """
        word = document.get_word_before_cursor()
        text = document.text_before_cursor.lower()

        # Only complete device names in certain contexts
        # e.g., after "check", "show", device names, etc.
        trigger_words = ["check", "show", "analyze", "display", "audit", "config", "device", "query"]
        should_complete = any(tw in text for tw in trigger_words) or len(word) >= 2

        if not should_complete:
            return

        # Trigger background fetch if cache is stale
        if self._should_refresh() and not self._fetching:
            self._fetching = True
            asyncio.create_task(self._background_fetch())

        # Use cached devices
        word_lower = word.lower()
        for device in self._cache:
            if device.lower().startswith(word_lower):
                yield Completion(
                    device,
                    start_position=-len(word),
                    display_meta="device",
                )

    async def _background_fetch(self):
        """Background fetch devices."""
        try:
            await self._fetch_devices()
        finally:
            self._fetching = False

    async def prefetch(self):
        """Prefetch devices on REPL startup."""
        await self._fetch_devices()

# Prompt style
PROMPT_STYLE = Style.from_dict({
    # User input
    "": "#ffffff",
    # Prompt prefix
    "username": "#00aa00 bold",
    "at": "#888888",
    "host": "#00aaff",
    "colon": "#888888",
    "path": "#aa00aa",
    "pound": "#00aa00 bold",
    # Bottom toolbar
    "bottom-toolbar": "bg:#222222 #aaaaaa",
    "bottom-toolbar.text": "#aaaaaa",
})


def get_toolbar_text() -> str:
    """Generate bottom toolbar text."""
    return " /h Help | /s Standard | /e Expert | /i Inspect | /c Clear | Ctrl+R Search"


# ============================================
# REPL Session
# ============================================
class REPLSession:
    """Interactive REPL session with prompt_toolkit.

    Features:
        - Command history (persisted to ~/.olav/history)
        - Fuzzy history search (Ctrl+R)
        - Auto-suggestions from history
        - Tab completion for commands

    Usage:
        async with REPLSession(client, console) as repl:
            while True:
                user_input = await repl.prompt()
                if user_input is None:
                    break
                # Process input...
    """

    def __init__(
        self,
        client: "OlavThinClient",
        console: Console,
        mode: str = "standard",
    ):
        self.client = client
        self.console = console
        self.mode = mode
        self.thread_id = f"cli-{int(asyncio.get_event_loop().time())}"

        # History file
        history_dir = Path.home() / ".olav"
        history_dir.mkdir(exist_ok=True)
        history_file = history_dir / "history"

        # Create dynamic device completer
        self.device_completer = DynamicDeviceCompleter(client)

        # Merge static and dynamic completers
        combined_completer = merge_completers([
            command_completer,
            self.device_completer,
        ])

        # Create prompt session
        self.session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=combined_completer,
            style=PROMPT_STYLE,
            complete_while_typing=True,
            enable_history_search=True,
            bottom_toolbar=get_toolbar_text,
        )

    async def __aenter__(self) -> "REPLSession":
        """Context manager entry - prefetch devices and show welcome."""
        from olav.cli.display import show_welcome_banner

        # Show welcome banner with OLAV logo and snowman
        show_welcome_banner(self.console)

        # Prefetch device names in background
        asyncio.create_task(self.device_completer.prefetch())
        return self

    async def __aexit__(self, *args) -> None:
        """Context manager exit."""
        pass

    def _get_prompt_message(self, hitl_pending: bool = False) -> list:
        """Generate prompt message with rich formatting."""
        if hitl_pending:
            return [
                ("class:username", "HITL"),
                ("class:colon", ": "),
            ]
        return [
            ("class:username", "You"),
            ("class:colon", ": "),
        ]

    async def prompt(self, hitl_pending: bool = False) -> str | None:
        """Get user input with prompt_toolkit.

        Args:
            hitl_pending: If True, shows HITL prompt

        Returns:
            User input string, or None if user wants to exit
        """
        try:
            # Run prompt in executor to not block async event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.session.prompt(
                    self._get_prompt_message(hitl_pending),
                ),
            )
            return result.strip() if result else ""
        except KeyboardInterrupt:
            return None
        except EOFError:
            return None

    def set_mode(self, mode: str) -> None:
        """Change operation mode.

        User can switch modes in TUI, but workflows are strictly separated:
        - Standard mode uses fast_path strategy
        - Expert mode uses SupervisorDrivenWorkflow
        - No automatic escalation between modes
        """
        if mode in MODE_OPTIONS:
            self.mode = mode
            if mode == "standard":
                self.console.print("[green]✓ Switched to Standard mode[/green] (fast path)")
            else:
                self.console.print("[green]✓ Switched to Expert mode[/green] (Supervisor-Driven L1-L4 analysis)")
        else:
            self.console.print(f"[yellow]Invalid mode. Options: {', '.join(MODE_OPTIONS)}[/yellow]")

    def show_help(self) -> None:
        """Display help information."""
        self.console.print()
        self.console.print("[bold cyan]OLAV CLI Commands[/bold cyan]")
        self.console.print()
        self.console.print("[cyan]/h[/cyan]           Show this help")
        self.console.print("[cyan]/q[/cyan]           Exit REPL (or Ctrl+D)")
        self.console.print("[cyan]/s[/cyan]           Switch to Standard mode (fast path)")
        self.console.print("[cyan]/e[/cyan]           Switch to Expert mode (Supervisor-Driven)")
        self.console.print("[cyan]/c[/cyan]           Clear screen")
        self.console.print("[cyan]/his[/cyan]         Show command history")
        self.console.print("[cyan]/info[/cyan]        Show session info")
        self.console.print()
        self.console.print(f"[dim]Current mode: [bold]{self.mode}[/bold][/dim]")
        self.console.print()
        self.console.print("[bold cyan]Keyboard Shortcuts[/bold cyan]")
        self.console.print()
        self.console.print("Ctrl+R        Search history")
        self.console.print("Ctrl+C        Cancel current input")
        self.console.print("Ctrl+D        Exit")
        self.console.print("Tab           Auto-complete")
        self.console.print("Up/Down       Navigate history")
        self.console.print()
        self.console.print("[bold cyan]Example Queries[/bold cyan]")
        self.console.print()
        for example in EXAMPLE_QUERIES:
            self.console.print(f"  - {example}")
        self.console.print()

    def show_history(self, limit: int = 20) -> None:
        """Display recent command history."""
        history_items = list(self.session.history.get_strings())[-limit:]
        if not history_items:
            self.console.print("[dim]No history yet[/dim]")
            return

        self.console.print(f"[bold]Recent Commands (last {len(history_items)}):[/bold]")
        for i, item in enumerate(history_items, 1):
            # Truncate long commands
            display = item[:60] + "..." if len(item) > 60 else item
            self.console.print(f"  {i}. {display}")

    def show_session_info(self) -> None:
        """Display current session information."""
        self.console.print()
        self.console.print("[bold cyan]Session Info[/bold cyan]")
        self.console.print()
        self.console.print(f"  Thread ID:  [dim]{self.thread_id}[/dim]")
        self.console.print(f"  Mode:       [bold]{self.mode}[/bold]")
        self.console.print(f"  Server:     [dim]{self.client.config.server_url}[/dim]")
        self.console.print(f"  Devices:    [dim]{len(self.device_completer._cache)} cached[/dim]")
        self.console.print()


# ============================================
# Command Handler
# ============================================
def handle_slash_command(repl: REPLSession, command: str) -> bool:
    """Handle slash commands.

    Args:
        repl: REPL session
        command: Full command string (including /)


    Returns:
        True if should exit REPL, False otherwise
    """
    parts = command[1:].lower().split()
    cmd = parts[0] if parts else ""
    args = parts[1:] if len(parts) > 1 else []

    # Exit commands
    if cmd in ("q", "exit", "quit"):
        repl.console.print("[yellow]Goodbye![/yellow]")
        return True

    # Help
    elif cmd in ("h", "help"):
        repl.show_help()

    # Standard mode
    elif cmd == "s":
        repl.set_mode("standard")

    # Expert mode
    elif cmd == "e":
        repl.set_mode("expert")

    # Clear screen
    elif cmd in ("c", "clear"):
        repl.console.clear()

    # History
    elif cmd in ("his", "history"):
        limit = int(args[0]) if args else 20
        repl.show_history(limit)

    # Session info
    elif cmd == "info":
        repl.show_session_info()

    else:
        repl.console.print(f"[yellow]Unknown command: /{cmd}[/yellow]")
        repl.console.print("[dim]Type /h for help[/dim]")

    return False
