"""OLAV Prompt Session - Enhanced CLI session using prompt-toolkit."""

from pathlib import Path
from typing import Callable, Optional

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.formatted_text import HTML
except ImportError:
    # Fallback if prompt-toolkit not installed
    PromptSession = None
    FileHistory = None
    AutoSuggestFromHistory = None
    WordCompleter = None
    KeyBindings = None
    HTML = None


class OlavPromptSession:
    """Enhanced OLAV prompt session with prompt-toolkit features.

    Features:
    - Persistent command history (agent_dir/.cli_history)
    - Auto-completion for commands and file names
    - Multi-line input support
    - History search with Ctrl+R
    - Syntax highlighting (optional)
    """

    def __init__(
        self,
        history_file: str | Path = None,
        enable_completion: bool = True,
        enable_history: bool = True,
        multiline: bool = True,
    ):
        """Initialize the prompt session.

        Args:
            history_file: Path to history file (defaults to agent_dir/.cli_history)
            enable_completion: Enable auto-completion
            enable_history: Enable history persistence
            multiline: Enable multi-line input
        """
        if history_file is None:
            from config.settings import settings
            history_file = Path(settings.agent_dir) / ".cli_history"
        
        self.history_file = Path(history_file)
        self.enable_completion = enable_completion
        self.enable_history = enable_history
        self.multiline = multiline

        # Create history file directory if needed
        if self.enable_history:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)

        self._session: Optional[PromptSession] = None
        self._init_session()

    def _init_session(self) -> None:
        """Initialize the prompt-toolkit session."""
        import sys
        
        # Check if stdin is a TTY (interactive terminal)
        # If not (piped input), fall back to basic input
        if not sys.stdin.isatty():
            print("Note: Non-interactive mode detected, using basic input")
            return
        
        if PromptSession is None:
            print("Warning: prompt-toolkit not installed, using basic input")
            return

        # Build command list for completion
        commands = [
            "/devices",
            "/skills",
            "/inspect",
            "/reload",
            "/clear",
            "/history",
            "/help",
            "/quit",
            "/exit",
        ]

        # Configure session
        session_kwargs: dict = {}

        if self.enable_history:
            session_kwargs["history"] = FileHistory(str(self.history_file))

        if self.enable_completion:
            session_kwargs["completer"] = WordCompleter(
                commands,
                ignore_case=True,
                sentence=True,
            )
            session_kwargs["auto_suggest"] = AutoSuggestFromHistory()

        # Set multiline mode based on constructor parameter
        session_kwargs["multiline"] = self.multiline

        # Create key bindings
        if KeyBindings is not None:
            kb = KeyBindings()

            @kb.add("c-c")
            def _(event):
                """Ctrl+C exits."""
                event.app.exit(exception=EOFError, style="class:abort")

            @kb.add("c-d")
            def _(event):
                """Ctrl+D exits."""
                event.app.exit(exception=EOFError)

            session_kwargs["key_bindings"] = kb

        try:
            self._session = PromptSession(**session_kwargs)
        except Exception as e:
            # Handle cases where Windows console is not available
            # (e.g., when stdin is piped or running in non-interactive mode)
            print(f"Warning: Could not initialize interactive prompt-toolkit: {type(e).__name__}")
            print("         Falling back to basic input mode")
            self._session = None

    async def prompt(self, message: str = "olav> ") -> str:
        """Get user input asynchronously.

        Args:
            message: Prompt message to display

        Returns:
            User input string
        """
        if self._session is None:
            # Fallback to basic input
            return input(message)

        try:
            # Use plain string prompt to avoid XML parsing issues
            result = await self._session.prompt_async(message)
            return result
        except (EOFError, KeyboardInterrupt):
            raise EOFError

    def prompt_sync(self, message: str = "olav> ") -> str:
        """Get user input synchronously.

        Args:
            message: Prompt message to display

        Returns:
            User input string
        """
        if self._session is None:
            return input(message)

        try:
            # Use plain string prompt to avoid XML parsing issues
            # (HTML formatting breaks when message contains > or <)
            result = self._session.prompt(message)
            return result
        except (EOFError, KeyboardInterrupt):
            raise EOFError

    def clear_history(self) -> None:
        """Clear command history."""
        if self.enable_history and self.history_file.exists():
            self.history_file.unlink()
