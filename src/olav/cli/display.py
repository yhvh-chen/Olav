"""OLAV CLI Display Components.

Rich-based UI components for the CLI:
- ThinkingTree: Real-time thinking process visualization
- HITLPanel: HITL approval interaction
- ProgressDisplay: Inspection progress bars
- ResultRenderer: Format and display results
- Dashboard: TUI dashboard mode
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from olav.cli.thin_client import HITLRequest, StreamEventType, ToolCall

if TYPE_CHECKING:
    from olav.cli.thin_client import OlavThinClient


# ============================================
# ASCII Art & Branding
# ============================================
OLAV_LOGO = """[bold blue] ██████  [/bold blue][bold cyan]██       [/bold cyan][bold green]  █████  [/bold green][bold magenta]██    ██[/bold magenta]
[bold blue]██    ██ [/bold blue][bold cyan]██       [/bold cyan][bold green] ██   ██ [/bold green][bold magenta]██    ██[/bold magenta]
[bold blue]██    ██ [/bold blue][bold cyan]██       [/bold cyan][bold green] ███████ [/bold green][bold magenta]██    ██[/bold magenta]
[bold blue]██    ██ [/bold blue][bold cyan]██       [/bold cyan][bold green] ██   ██ [/bold green][bold magenta] ██  ██ [/bold magenta]
[bold blue] ██████  [/bold blue][bold cyan]████████ [/bold cyan][bold green] ██   ██ [/bold green][bold magenta]  ████  [/bold magenta]"""

# Big OLAV logo (8 lines tall, using larger block characters)
OLAV_LOGO_BIG = """[bold blue] ▄██████▄  [/bold blue][bold cyan]██        [/bold cyan][bold green]  ▄█████▄  [/bold green][bold magenta]██      ██[/bold magenta]
[bold blue]██      ██ [/bold blue][bold cyan]██        [/bold cyan][bold green] ██     ██ [/bold green][bold magenta]██      ██[/bold magenta]
[bold blue]██      ██ [/bold blue][bold cyan]██        [/bold cyan][bold green] ██     ██ [/bold green][bold magenta]██      ██[/bold magenta]
[bold blue]██      ██ [/bold blue][bold cyan]██        [/bold cyan][bold green] █████████ [/bold green][bold magenta]██      ██[/bold magenta]
[bold blue]██      ██ [/bold blue][bold cyan]██        [/bold cyan][bold green] ██     ██ [/bold green][bold magenta] ██    ██ [/bold magenta]
[bold blue]██      ██ [/bold blue][bold cyan]██        [/bold cyan][bold green] ██     ██ [/bold green][bold magenta]  ██  ██  [/bold magenta]
[bold blue] ▀██████▀  [/bold blue][bold cyan]█████████ [/bold cyan][bold green] ██     ██ [/bold green][bold magenta]   ████   [/bold magenta]"""

# Small snowman (7 lines, same height as big logo)
SNOWMAN_SMALL = """[cyan]  ❄ [/cyan][bold white]⛄[/bold white][cyan] ❄[/cyan]
[bold white]  .~~~.[/bold white]
[bold white] ( [cyan]°[/cyan] [cyan]°[/cyan] )[/bold white]
[bold white]  ( [orange1]>[/orange1] )[/bold white]
[bold white] ([red]~~~~~[/red])[/bold white]
[bold white]  (   )[/bold white]
[dim white]  ❆ ❅ ❆[/dim white]"""

# Legacy snowman (for backward compatibility)
SNOWMAN_ASCII = SNOWMAN_SMALL

SNOWMAN_MINI = "[bold white]⛄[/bold white] [cyan]❄[/cyan] [white]❆[/white] [cyan]❄[/cyan]"

WINTER_BORDER = "[cyan]❄[/cyan] [white]❆[/white] [blue]❅[/blue]"


def get_olav_banner() -> Text:
    """Get colorful OLAV banner."""
    return Text.from_markup(OLAV_LOGO)


def get_snowman() -> Text:
    """Get snowman ASCII art."""
    return Text.from_markup(SNOWMAN_ASCII)


def get_snowman_small() -> Text:
    """Get small snowman with snowflakes."""
    return Text.from_markup(SNOWMAN_MINI)


# ============================================
# Thinking Tree
# ============================================
@dataclass
class ThinkingStep:
    """A step in the thinking process."""

    id: str
    description: str
    status: str = "pending"  # pending, running, success, error
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    children: list["ThinkingStep"] = field(default_factory=list)


class ThinkingTree:
    """Real-time visualization of agent thinking process.

    Uses Rich Tree with Live display for dynamic updates.
    Supports ReAct agent pattern with hypothesis-verification flow.

    Example:
        with ThinkingTree(console) as tree:
            tree.add_step("Analyzing query...")
            tree.add_tool_call("suzieq_query", {"table": "bgp"})
            tree.mark_tool_complete("suzieq_query", success=True)
    """

    TOOL_ICONS = {
        "suzieq_query": "📊",
        "suzieq_schema_search": "🔍",
        "netconf_tool": "🔧",
        "netconf_execute": "🔧",
        "cli_tool": "💻",
        "cli_execute": "💻",
        "netbox_api": "📦",
        "rag_search": "📚",
    }

    STATUS_ICONS = {
        "pending": "⏳",
        "running": "🔄",
        "success": "✅",
        "error": "❌",
    }

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self.tree = Tree("[bold cyan]🧠 Thinking Process[/bold cyan]")
        self.live: Live | None = None
        self.tool_nodes: dict[str, Any] = {}
        self.current_step: Any = None
        self.start_time = time.time()
        self.step_count = 0
        self.hypothesis_node: Any = None
        # Streaming thinking support
        self._thinking_buffer: str = ""
        self._thinking_node: Any = None

    def __enter__(self) -> "ThinkingTree":
        """Start live display."""
        self.live = Live(
            self.tree,
            console=self.console,
            refresh_per_second=10,
            transient=False,  # Keep visible after exit
        )
        self.live.__enter__()
        return self

    def __exit__(self, *args) -> None:
        """Stop live display."""
        if self.live:
            # Add summary
            elapsed = time.time() - self.start_time
            self.tree.add(f"[dim]⏱️ Total time: {elapsed:.2f}s[/dim]")
            self.live.__exit__(*args)

    def add_thinking(self, text: str, streaming: bool = True) -> None:
        """Add a thinking step.

        Args:
            text: The thinking content (can be a token or full text)
            streaming: If True, accumulates text into a single node (for streaming tokens).
                      If False, creates a new node for each call (legacy behavior).
        """
        if streaming:
            # Streaming mode: accumulate into single node
            self._thinking_buffer += text

            # Update or create the thinking node
            display_text = self._thinking_buffer
            # Truncate display if too long (keep last 200 chars for display)
            if len(display_text) > 200:
                display_text = "..." + display_text[-197:]

            if self._thinking_node is None:
                self._thinking_node = self.tree.add(f"[yellow]💭 {display_text}[/yellow]")
            else:
                # Update existing node label
                self._thinking_node.label = f"[yellow]💭 {display_text}[/yellow]"
            self._refresh()
            return

        # Legacy non-streaming mode
        self.step_count += 1
        # Detect hypothesis-related thinking
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["hypothes", "假设", "可能", "maybe", "could be"]):
            self.current_step = self.tree.add(f"[magenta]🔮 {text}[/magenta]")
            self.hypothesis_node = self.current_step
        elif any(kw in text_lower for kw in ["verify", "验证", "check", "检查", "test"]):
            self.current_step = self.tree.add(f"[cyan]🔬 {text}[/cyan]")
        elif any(kw in text_lower for kw in ["evidence", "证据", "found", "发现", "result"]):
            self.current_step = self.tree.add(f"[green]📌 {text}[/green]")
        elif any(kw in text_lower for kw in ["调用", "calling", "query", "查询"]):
            self.current_step = self.tree.add(f"[blue]⚡ {text}[/blue]")
        else:
            self.current_step = self.tree.add(f"[yellow]💭 {text}[/yellow]")
        self._refresh()

    def finalize_thinking(self) -> None:
        """Finalize streaming thinking - show full content summary.

        Call this when thinking is complete to update the node with final content.
        """
        if self._thinking_buffer and self._thinking_node:
            # Show word count summary instead of truncated text
            char_count = len(self._thinking_buffer)
            # Keep a brief preview
            preview = self._thinking_buffer[:100].replace('\n', ' ')
            if len(self._thinking_buffer) > 100:
                preview += "..."
            self._thinking_node.label = f"[yellow]💭 思考 ({char_count}字): {preview}[/yellow]"
            self._refresh()
        # Reset buffer for next thinking session
        self._thinking_buffer = ""
        self._thinking_node = None

    def add_hypothesis(self, hypothesis: str, confidence: float = 0.0) -> None:
        """Add a hypothesis step (ReAct pattern)."""
        conf_color = "green" if confidence >= 0.8 else "yellow" if confidence >= 0.5 else "red"
        self.hypothesis_node = self.tree.add(
            f"[magenta]🔮 Hypothesis:[/magenta] {hypothesis} "
            f"[{conf_color}]({confidence:.0%})[/{conf_color}]"
        )
        self._refresh()

    def add_evidence(self, evidence: str, supports: bool = True) -> None:
        """Add evidence for/against hypothesis."""
        icon = "✓" if supports else "✗"
        color = "green" if supports else "red"
        if self.hypothesis_node:
            self.hypothesis_node.add(f"[{color}]{icon} {evidence}[/{color}]")
        else:
            self.tree.add(f"[{color}]📌 {icon} {evidence}[/{color}]")
        self._refresh()

    def add_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        """Add a tool call node."""
        icon = self.TOOL_ICONS.get(tool_name, "🔧")

        # Format args preview
        args_preview = ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])
        if len(args_preview) > 50:
            args_preview = args_preview[:47] + "..."

        node = self.tree.add(f"[yellow]{icon} {tool_name}[/yellow]")
        node.add(f"[dim]{args_preview}[/dim]")

        self.tool_nodes[tool_name] = {
            "node": node,
            "start_time": time.time(),
        }
        self._refresh()

    def mark_tool_complete(
        self,
        tool_name: str,
        success: bool = True,
        result_preview: str | None = None,
    ) -> None:
        """Mark a tool call as complete."""
        if tool_name not in self.tool_nodes:
            return

        tool_info = self.tool_nodes[tool_name]
        node = tool_info["node"]
        elapsed = time.time() - tool_info["start_time"]

        icon = self.TOOL_ICONS.get(tool_name, "🔧")
        status = "✅" if success else "❌"

        node.label = Text.from_markup(
            f"[{'green' if success else 'red'}]{icon} {tool_name} {status}[/] "
            f"[dim]({elapsed:.2f}s)[/dim]"
        )

        if result_preview:
            preview = result_preview[:100] + "..." if len(result_preview) > 100 else result_preview
            node.add(f"[dim]→ {preview}[/dim]")

        self._refresh()

    def add_error(self, message: str) -> None:
        """Add an error node."""
        self.tree.add(f"[red]❌ Error: {message}[/red]")
        self._refresh()

    def _refresh(self) -> None:
        """Refresh the live display."""
        if self.live:
            self.live.update(self.tree)


# ============================================
# HITL Panel
# ============================================
class HITLPanel:
    """Display HITL approval requests and handle user input.

    Example:
        panel = HITLPanel(console)
        decision = panel.prompt(hitl_request)
        # decision is "Y", "N", or modification text
    """

    RISK_COLORS = {
        "low": "green",
        "medium": "yellow",
        "high": "red",
    }

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def display(self, request: HITLRequest) -> None:
        """Display HITL request details."""
        risk_color = self.RISK_COLORS.get(request.risk_level, "yellow")

        # Build info table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="bold")
        table.add_column("Value")

        table.add_row("Workflow", request.workflow_type)
        table.add_row("Operation", request.operation)
        table.add_row("Target Device", request.target_device)
        table.add_row("Risk Level", f"[{risk_color}]{request.risk_level.upper()}[/{risk_color}]")

        # Commands list
        if request.commands:
            commands_text = "\n".join(f"  • {cmd}" for cmd in request.commands[:5])
            if len(request.commands) > 5:
                commands_text += f"\n  ... {len(request.commands)} commands total"
            table.add_row("Commands", commands_text)

        # Reasoning
        if request.reasoning:
            table.add_row("AI Reasoning", request.reasoning[:200])

        # Create panel
        panel = Panel(
            table,
            title="[bold red]⚠️ HITL Approval Request[/bold red]",
            border_style="red" if request.risk_level == "high" else "yellow",
            subtitle="[dim]Your approval is required to continue[/dim]",
        )

        self.console.print()
        self.console.print(panel)

    def display_execution_plan(self, request: HITLRequest) -> None:
        """Display execution plan with todo items."""
        if not request.execution_plan and not request.todos:
            return

        self.console.print()
        self.console.print("=" * 60)
        self.console.print("[bold]📋 Execution Plan[/bold]")
        self.console.print("=" * 60)

        if request.execution_plan:
            plan = request.execution_plan

            # Summary
            if plan.get("summary"):
                self.console.print(plan["summary"])
                self.console.print("-" * 60)

            # Feasible tasks
            feasible = plan.get("feasible_tasks", [])
            if feasible:
                self.console.print(f"\n[green]✅ Feasible Tasks ({len(feasible)}):[/green]")
                for task_id in feasible:
                    task_desc = self._get_task_description(task_id, request.todos)
                    self.console.print(f"  • Task {task_id}: {task_desc}")

            # Uncertain tasks
            uncertain = plan.get("uncertain_tasks", [])
            if uncertain:
                self.console.print(f"\n[yellow]⚠️ Uncertain Tasks ({len(uncertain)}):[/yellow]")
                for task_id in uncertain:
                    task_desc = self._get_task_description(task_id, request.todos)
                    self.console.print(f"  • Task {task_id}: {task_desc}")

            # Infeasible tasks
            infeasible = plan.get("infeasible_tasks", [])
            if infeasible:
                self.console.print(f"\n[red]❌ Infeasible Tasks ({len(infeasible)}):[/red]")
                for task_id in infeasible:
                    task_desc = self._get_task_description(task_id, request.todos)
                    self.console.print(f"  • Task {task_id}: {task_desc}")

        self.console.print("=" * 60)

    def _get_task_description(self, task_id: int, todos: list[dict] | None) -> str:
        """Get task description from todos list."""
        if not todos:
            return "(no description)"

        for todo in todos:
            if isinstance(todo, dict) and todo.get("id") == task_id:
                return todo.get("task", "(no description)")

        return "(no description)"

    def prompt(self, request: HITLRequest) -> str:
        """Display request and prompt for user decision.

        Returns:
            "Y" for approve, "N" for reject, or modification text
        """
        self.display(request)
        self.display_execution_plan(request)

        self.console.print()
        self.console.print("[bold]Choose an action:[/bold]")
        self.console.print("  [green]Y / yes[/green]  - Approve")
        self.console.print("  [red]N / no[/red]   - Reject")
        self.console.print("  [cyan]Other[/cyan]    - Modify request")
        self.console.print()

        user_input = self.console.input("[bold]Your decision: [/bold]").strip()

        if user_input.lower() in ("y", "yes", "approve", "批准"):
            return "Y"
        elif user_input.lower() in ("n", "no", "reject", "拒绝", "abort"):
            return "N"
        else:
            return user_input


# ============================================
# Progress Display
# ============================================
class InspectionProgress:
    """Display inspection progress with multiple bars.

    Shows:
    - Overall progress (total checks)
    - Current batch progress (devices in batch)
    - Current device progress (checks on device)
    """

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        )
        self.tasks: dict[str, Any] = {}

    def __enter__(self) -> "InspectionProgress":
        self.progress.__enter__()
        return self

    def __exit__(self, *args) -> None:
        self.progress.__exit__(*args)

    def add_overall(self, total: int, description: str = "Overall") -> None:
        """Add overall progress bar."""
        self.tasks["overall"] = self.progress.add_task(description, total=total)

    def add_device(self, device_name: str, total_checks: int) -> None:
        """Add device-level progress bar."""
        self.tasks["device"] = self.progress.add_task(
            f"📡 {device_name}", total=total_checks
        )

    def update_overall(self, advance: int = 1) -> None:
        """Advance overall progress."""
        if "overall" in self.tasks:
            self.progress.update(self.tasks["overall"], advance=advance)

    def update_device(self, advance: int = 1) -> None:
        """Advance device progress."""
        if "device" in self.tasks:
            self.progress.update(self.tasks["device"], advance=advance)

    def complete_device(self) -> None:
        """Complete and remove device progress bar."""
        if "device" in self.tasks:
            self.progress.remove_task(self.tasks["device"])
            del self.tasks["device"]


# ============================================
# Result Renderer
# ============================================
class ResultRenderer:
    """Render execution results with proper formatting.

    Handles:
    - Markdown text
    - Data tables
    - JSON/YAML
    - Error messages
    """

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def render_message(self, content: str, role: str = "assistant") -> None:
        """Render a chat message."""
        if role in ("assistant", "ai"):
            # Unescape literal \n
            content = content.replace("\\n", "\n").replace("\\t", "\t")

            panel = Panel(
                Markdown(content),
                title="[bold green]🤖 OLAV[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            self.console.print(panel)

        elif role in ("user", "human"):
            panel = Panel(
                content,
                title="[bold cyan]👤 You[/bold cyan]",
                border_style="cyan",
                padding=(0, 2),
            )
            self.console.print(panel)

    def render_table(
        self,
        data: list[dict],
        title: str | None = None,
        max_rows: int = 20,
    ) -> None:
        """Render data as a table."""
        if not data:
            self.console.print("[dim]No data[/dim]")
            return

        # Get columns from first row
        columns = list(data[0].keys())

        table = Table(title=title, show_lines=True)
        for col in columns:
            table.add_column(col)

        for row in data[:max_rows]:
            table.add_row(*[str(row.get(col, "")) for col in columns])

        if len(data) > max_rows:
            table.caption = f"[dim]Showing {max_rows} of {len(data)} rows[/dim]"

        self.console.print(table)

    def render_json(self, data: Any, title: str | None = None) -> None:
        """Render JSON data with syntax highlighting."""
        import json

        from rich.syntax import Syntax

        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)

        if title:
            self.console.print(f"[bold]{title}[/bold]")
        self.console.print(syntax)

    def render_error(self, message: str, details: str | None = None) -> None:
        """Render an error message."""
        content = f"[bold red]{message}[/bold red]"
        if details:
            content += f"\n\n[dim]{details}[/dim]"

        panel = Panel(
            content,
            title="[bold red]❌ Error[/bold red]",
            border_style="red",
        )
        self.console.print(panel)

    def render_success(self, message: str) -> None:
        """Render a success message."""
        self.console.print(f"[bold green]✅ {message}[/bold green]")

    def render_warning(self, message: str) -> None:
        """Render a warning message."""
        self.console.print(f"[bold yellow]⚠️ {message}[/bold yellow]")

    def render_info(self, message: str) -> None:
        """Render an info message."""
        self.console.print(f"[cyan]ℹ️ {message}[/cyan]")

    def render_tool_summary(self, tool_calls: list[ToolCall]) -> None:
        """Render a summary of tool calls."""
        if not tool_calls:
            return

        table = Table(title="Tool Calls", show_header=True)
        table.add_column("Tool", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")

        for tool in tool_calls:
            status = "✅" if tool.success else "❌"
            duration = f"{tool.duration_ms:.0f}ms" if tool.duration_ms else "-"
            table.add_row(tool.name, status, duration)

        self.console.print(table)


# ============================================
# Dashboard (TUI Mode)
# ============================================
class Dashboard:
    """Full-screen TUI dashboard for OLAV with chat interface.

    Features:
    - Chat-style conversation interface
    - Real-time streaming responses
    - Colorful OLAV branding with snowman

    Usage:
        dashboard = Dashboard(client, console)
        await dashboard.run()
    """

    def __init__(
        self,
        client: "OlavThinClient",
        console: Console | None = None,
        mode: str = "standard",
    ):
        self.client = client
        self.console = console or Console()
        self.mode = mode
        self.running = False
        self._chat_history: list[tuple[str, str, str]] = []  # (role, content, timestamp)

    def _print_header(self) -> None:
        """Print header with OLAV logo and snowman."""
        # Combine logo and snowman side by side
        header_table = Table.grid(padding=1)
        header_table.add_column(justify="center", ratio=2)
        header_table.add_column(justify="center", ratio=1)

        logo_text = Text.from_markup(OLAV_LOGO)
        snowman_text = Text.from_markup(SNOWMAN_ASCII)

        header_table.add_row(logo_text, snowman_text)

        # Add subtitle with mode indicator
        subtitle = Text()
        subtitle.append("\n")
        subtitle.append("❄ ", style="cyan")
        subtitle.append("Omni-Layer Autonomous Verifier", style="bold white")
        subtitle.append(" ❄ ", style="cyan")
        mode_style = "bold yellow" if self.mode == "expert" else "bold green"
        subtitle.append(f"[{self.mode.upper()}]", style=mode_style)
        subtitle.append("\n")
        subtitle.append("❆ ", style="white")
        subtitle.append("Type your query, ", style="dim")
        subtitle.append("/h", style="bold cyan")
        subtitle.append(" for help, ", style="dim")
        subtitle.append("Ctrl+C", style="bold cyan")
        subtitle.append(" to exit", style="dim")
        subtitle.append(" ❆", style="white")

        content = Group(
            Align.center(header_table),
            Align.center(subtitle),
        )

        panel = Panel(
            content,
            border_style="cyan",
            padding=(0, 2),
        )
        self.console.print(panel)

    def _print_chat_history(self) -> None:
        """Print recent chat history."""
        if not self._chat_history:
            return

        self.console.print()
        for role, msg, ts in self._chat_history[-10:]:  # Show last 10 messages
            if role == "user":
                self.console.print(f"[dim]{ts}[/dim] [bold cyan]You:[/bold cyan] {msg}")
            elif role == "assistant":
                # Handle multi-line responses
                lines = msg.split("\n")
                self.console.print(f"[dim]{ts}[/dim] [bold green]OLAV:[/bold green] {lines[0]}")
                for line in lines[1:]:
                    self.console.print(f"       [green]{line}[/green]")
            elif role == "thinking":
                self.console.print(f"[dim]{ts}[/dim] [yellow]💭 {msg}[/yellow]")
            elif role == "tool":
                self.console.print(f"[dim]{ts}[/dim] [magenta]🔧 {msg}[/magenta]")
        self.console.print()

    def add_message(self, role: str, content: str) -> None:
        """Add a message to chat history."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._chat_history.append((role, content, timestamp))
        # Keep only last 100 messages
        if len(self._chat_history) > 100:
            self._chat_history = self._chat_history[-100:]

    def _refresh_display(self) -> None:
        """Clear screen and redraw header + history."""
        self.console.clear()
        self._print_header()
        self._print_chat_history()

    async def run(self) -> None:
        """Run the dashboard in interactive mode."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.styles import Style as PTStyle

        self.running = True

        # Create styled prompt session
        style = PTStyle.from_dict({
            "prompt": "cyan bold",
        })
        session: PromptSession = PromptSession(style=style)

        # Initial display
        self._refresh_display()

        try:
            while self.running:
                # Get user input using prompt_toolkit
                try:
                    user_input = await session.prompt_async(
                        HTML("<cyan><b>❯ </b></cyan>"),
                    )
                except (EOFError, KeyboardInterrupt):
                    self.running = False
                    break

                user_input = user_input.strip()
                if not user_input:
                    continue

                # Handle slash commands
                if user_input.startswith("/"):
                    if user_input in ("/q", "/quit", "/exit"):
                        self.running = False
                        break
                    elif user_input in ("/h", "/help"):
                        self.add_message("assistant", "Commands: /q quit, /h help, /s standard, /e expert, /c clear, /status system")
                        self._refresh_display()
                        continue
                    elif user_input in ("/status", "/st"):
                        await self._show_status_inline()
                        continue
                    elif user_input == "/s":
                        self.mode = "standard"
                        self.add_message("assistant", "✅ Switched to Standard mode")
                        self._refresh_display()
                        continue
                    elif user_input == "/e":
                        self.mode = "expert"
                        self.add_message("assistant", "✅ Switched to Expert mode (Deep Dive)")
                        self._refresh_display()
                        continue
                    elif user_input in ("/c", "/clear"):
                        self._chat_history.clear()
                        self._refresh_display()
                        continue
                    else:
                        self.add_message("assistant", f"Unknown command: {user_input}. Type /h for help.")
                        self._refresh_display()
                        continue

                # Add user message and refresh
                self.add_message("user", user_input)
                self._refresh_display()

                # Show thinking indicator
                self.console.print("[yellow]💭 Thinking...[/yellow]")

                # Send query and stream response
                try:
                    import uuid
                    thread_id = str(uuid.uuid4())
                    full_response = ""

                    async for event in self.client.chat_stream(user_input, thread_id=thread_id, mode=self.mode):
                        event_type = event.type if hasattr(event, "type") else None

                        if event_type == StreamEventType.TOOL_START:
                            tool_name = event.data.get("name", "tool") if hasattr(event, "data") else "tool"
                            self.console.print(f"[magenta]🔧 Calling {tool_name}...[/magenta]")
                        elif event_type == StreamEventType.TOOL_END:
                            tool_name = event.data.get("name", "tool") if hasattr(event, "data") else "tool"
                            success = event.data.get("success", True) if hasattr(event, "data") else True
                            icon = "✅" if success else "❌"
                            self.console.print(f"[magenta]{icon} {tool_name} completed[/magenta]")
                        elif event_type == StreamEventType.TOKEN:
                            token = event.data.get("content", "") if hasattr(event, "data") else ""
                            if token:
                                full_response += token
                                # Print token incrementally
                                self.console.print(token, end="")
                        elif event_type == StreamEventType.MESSAGE:
                            # Complete message (from guard rejection or final response)
                            message = event.data.get("content", "") if hasattr(event, "data") else ""
                            if message:
                                full_response = message
                                self.console.print(message)
                        elif event_type == StreamEventType.THINKING:
                            thought = event.data.get("content", "") if hasattr(event, "data") else ""
                            if thought:
                                self.console.print(f"[dim yellow]💭 {thought[:80]}...[/dim yellow]")

                    # Add newline after streaming tokens
                    if full_response:
                        self.console.print()

                    # Add response to history
                    if full_response:
                        self.add_message("assistant", full_response.strip())
                    else:
                        self.add_message("assistant", "[dim]No response received[/dim]")

                    # Refresh to show clean history
                    self._refresh_display()

                except Exception as e:
                    self.add_message("assistant", f"[red]Error: {e}[/red]")
                    self._refresh_display()

        except KeyboardInterrupt:
            pass

        self.console.print()
        self.console.print("[yellow]👋 Dashboard closed. Goodbye![/yellow]")

    def stop(self) -> None:
        """Stop the dashboard."""
        self.running = False

    async def _show_status_inline(self) -> None:
        """Show system status inline in dashboard."""
        from rich.panel import Panel

        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]OLAV System Status[/bold cyan]",
            border_style="cyan",
        ))

        # Server health
        self.console.print("[bold]📊 Server Status[/bold]")
        try:
            health = await self.client.health()
            status_icon = "🟢" if health.status == "healthy" else "🔴"
            self.console.print(f"  Status:       {status_icon} {health.status}")
            self.console.print(f"  Version:      {health.version}")
            self.console.print(f"  Environment:  {health.environment}")
            orchestrator = "✅ Ready" if health.orchestrator_ready else "❌ Not ready"
            self.console.print(f"  Orchestrator: {orchestrator}")
        except Exception as e:
            self.console.print(f"  [red]❌ Cannot connect to server: {e}[/red]")
            return

        self.console.print()

        # Devices
        self.console.print("[bold]📡 Devices[/bold]")
        try:
            devices = await self.client.get_device_names()
            self.console.print(f"  Total: {len(devices)} devices")
            if devices and len(devices) <= 10:
                for device in devices:
                    self.console.print(f"    • {device}")
            elif devices:
                for device in devices[:5]:
                    self.console.print(f"    • {device}")
                self.console.print(f"    ... and {len(devices) - 5} more")
        except Exception as e:
            self.console.print(f"  [yellow]⚠ Cannot fetch devices: {e}[/yellow]")

        self.console.print()

        # SuzieQ tables
        self.console.print("[bold]📊 SuzieQ Tables[/bold]")
        try:
            tables = await self.client.get_suzieq_tables()
            self.console.print(f"  Total: {len(tables)} tables")
            if tables and len(tables) <= 10:
                self.console.print(f"  Tables: {', '.join(tables)}")
            elif tables:
                self.console.print(f"  Tables: {', '.join(tables[:10])}, ...")
        except Exception as e:
            self.console.print(f"  [yellow]⚠ Cannot fetch tables: {e}[/yellow]")

        self.console.print()
        self.add_message("assistant", "✅ Status check complete")


def show_welcome_banner(console: Console | None = None) -> None:
    """Show welcome banner with OLAV logo and snowman."""
    console = console or Console()

    # Create welcome display with big logo and small snowman
    welcome_table = Table.grid(padding=2)
    welcome_table.add_column(justify="center", ratio=3)
    welcome_table.add_column(justify="center", ratio=1)

    logo = Text.from_markup(OLAV_LOGO_BIG)
    snowman = Text.from_markup(SNOWMAN_SMALL)

    welcome_table.add_row(logo, snowman)

    # Subtitle
    subtitle = Text()
    subtitle.append("\n")
    subtitle.append("❄ ❆ ❅ ", style="cyan")
    subtitle.append("Welcome to OLAV CLI", style="bold white")
    subtitle.append(" ❅ ❆ ❄", style="cyan")
    subtitle.append("\n")
    subtitle.append("         NetAIChatOps\n", style="dim")
    subtitle.append("Type ", style="dim")
    subtitle.append("/h", style="bold cyan")
    subtitle.append(" for help\n", style="dim")

    panel = Panel(
        Group(
            Align.center(welcome_table),
            Align.center(subtitle),
        ),
        border_style="cyan",
        title=f"{WINTER_BORDER} OLAV {WINTER_BORDER}",
        subtitle=f"{WINTER_BORDER}",
    )

    console.print(panel)
