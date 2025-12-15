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
    children: list[ThinkingStep] = field(default_factory=list)


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

    def __init__(self, console: Console | None = None) -> None:
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

    def __enter__(self) -> ThinkingTree:
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
        if any(kw in text_lower for kw in ["hypothes", "maybe", "could be", "possibly", "might"]):
            self.current_step = self.tree.add(f"[magenta]🔮 {text}[/magenta]")
            self.hypothesis_node = self.current_step
        elif any(kw in text_lower for kw in ["verify", "check", "test", "validate"]):
            self.current_step = self.tree.add(f"[cyan]🔬 {text}[/cyan]")
        elif any(kw in text_lower for kw in ["evidence", "found", "result", "discover"]):
            self.current_step = self.tree.add(f"[green]📌 {text}[/green]")
        elif any(kw in text_lower for kw in ["calling", "query", "invoke", "tool"]):
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
            preview = self._thinking_buffer[:100].replace("\n", " ")
            if len(self._thinking_buffer) > 100:
                preview += "..."
            self._thinking_node.label = f"[yellow]💭 Thinking ({char_count} chars): {preview}[/yellow]"
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

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def display(self, request: HITLRequest) -> None:
        """Display HITL request details."""
        risk_color = self.RISK_COLORS.get(request.risk_level, "yellow")

        # Check if we have a config_plan with text content (from device_execution workflow)
        plan_text = None
        if request.execution_plan:
            if isinstance(request.execution_plan, dict):
                plan_text = request.execution_plan.get("plan")
            elif isinstance(request.execution_plan, str):
                plan_text = request.execution_plan

        # If we have plan text, display it directly
        if plan_text:
            panel = Panel(
                Markdown(plan_text) if plan_text.startswith("#") or "**" in plan_text else plan_text,
                title="[bold red]⚠️ HITL Approval Request[/bold red]",
                border_style="yellow",
                subtitle=f"[dim]Workflow: {request.workflow_type or 'device_execution'}[/dim]",
            )
            self.console.print()
            self.console.print(panel)
            return

        # Fallback: Build structured info table
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

        if user_input.lower() in ("y", "yes", "approve"):
            return "Y"
        if user_input.lower() in ("n", "no", "reject", "abort"):
            return "N"
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

    def __init__(self, console: Console | None = None) -> None:
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

    def __enter__(self) -> InspectionProgress:
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

    def __init__(self, console: Console | None = None) -> None:
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
# Debug Output Renderer
# ============================================
@dataclass
class DebugInfo:
    """Collected debug information from a query."""

    tool_calls: list[dict] = field(default_factory=list)
    thinking_steps: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    @property
    def duration_ms(self) -> float:
        """Calculate total duration in milliseconds."""
        if self.end_time > 0:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    def add_tool_call(self, tool_info: dict) -> None:
        """Record a tool call."""
        self.tool_calls.append({
            **tool_info,
            "timestamp": time.time(),
        })

    def add_thinking(self, content: str) -> None:
        """Record a thinking step."""
        if content.strip():
            self.thinking_steps.append(content.strip())

    def finalize(self) -> None:
        """Mark end of query processing."""
        self.end_time = time.time()


class DebugRenderer:
    """Render debug output for --debug mode.

    Displays:
    - Tool calls with args and duration
    - Thinking steps (if captured)
    - Timing breakdown
    """

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def render(self, debug_info: DebugInfo) -> None:
        """Render complete debug output."""
        self.console.print()
        self.console.print(Panel(
            self._build_debug_content(debug_info),
            title="[bold magenta]🔍 Debug Output[/bold magenta]",
            border_style="magenta",
            padding=(1, 2),
        ))

    def _build_debug_content(self, debug_info: DebugInfo) -> Group:
        """Build debug content as Rich Group."""
        elements = []

        # Summary
        summary = Text()
        summary.append("Total Duration: ", style="bold")
        summary.append(f"{debug_info.duration_ms:.1f}ms", style="cyan")
        summary.append("  |  ")
        summary.append("Tool Calls: ", style="bold")
        summary.append(str(len(debug_info.tool_calls)), style="cyan")
        elements.append(summary)
        elements.append(Text())  # Blank line

        # Tool calls table
        if debug_info.tool_calls:
            table = Table(
                title="Tool Invocations",
                show_header=True,
                header_style="bold cyan",
                border_style="dim",
            )
            table.add_column("#", style="dim", width=3)
            table.add_column("Tool", style="green")
            table.add_column("Arguments", max_width=50)
            table.add_column("Duration", justify="right", style="yellow")
            table.add_column("Status", justify="center")

            for i, tool in enumerate(debug_info.tool_calls, 1):
                args_str = self._format_args(tool.get("args", {}))
                duration = tool.get("duration_ms", 0)
                duration_str = f"{duration:.0f}ms" if duration else "-"
                status = "✅" if tool.get("success", True) else "❌"

                table.add_row(
                    str(i),
                    tool.get("display_name") or tool.get("name", "unknown"),
                    args_str,
                    duration_str,
                    status,
                )

            elements.append(table)

        # Thinking steps (collapsed summary)
        if debug_info.thinking_steps:
            elements.append(Text())
            thinking_summary = Text()
            thinking_summary.append("Thinking Steps: ", style="bold")
            thinking_summary.append(f"{len(debug_info.thinking_steps)} steps captured", style="dim")
            elements.append(thinking_summary)

        return Group(*elements)

    def _format_args(self, args: dict, max_len: int = 50) -> str:
        """Format tool arguments for display."""
        if not args:
            return "-"

        parts = []
        for key, value in args.items():
            if isinstance(value, str) and len(value) > 20:
                value = value[:17] + "..."
            parts.append(f"{key}={value}")

        result = ", ".join(parts)
        if len(result) > max_len:
            result = result[:max_len - 3] + "..."
        return result


# ============================================
# Dashboard (TUI Mode)
# ============================================
class Dashboard:
    """Full-screen TUI dashboard for OLAV with chat interface.

    Features:
    - Chat-style conversation interface
    - Real-time streaming responses
    - Colorful OLAV branding with snowman
    - Session memory (same thread_id for conversation continuity)

    Usage:
        dashboard = Dashboard(client, console)
        await dashboard.run()
    """

    def __init__(
        self,
        client: OlavThinClient,
        console: Console | None = None,
        mode: str = "standard",
        show_banner: bool = True,
    ) -> None:
        import uuid
        self.client = client
        self.console = console or Console()
        self.mode = mode
        self.show_banner = show_banner
        self.running = False
        self._chat_history: list[tuple[str, str, str]] = []  # (role, content, timestamp)
        self._activity_log: list[tuple[str, str]] = []  # (timestamp, message) for test compat
        # Use a single thread_id for the entire session (context memory)
        self._session_thread_id = f"dashboard-{uuid.uuid4().hex[:8]}"

    def add_activity(self, message: str) -> None:
        """Add activity to the log (for test compatibility)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._activity_log.append((timestamp, message))

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
        subtitle.append("NetAIChatOps", style="bold white")
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
        if self.show_banner:
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
                    if user_input in ("/h", "/help"):
                        self.add_message("assistant", "Commands: /q quit, /h help, /s standard, /e expert, /c clear, /status system")
                        self._refresh_display()
                        continue
                    if user_input in ("/status", "/st"):
                        await self._show_status_inline()
                        continue
                    if user_input == "/s":
                        self.mode = "standard"
                        self.add_message("assistant", "✅ Switched to Standard mode")
                        self._refresh_display()
                        continue
                    if user_input == "/e":
                        self.mode = "expert"
                        self.add_message("assistant", "✅ Switched to Expert mode (Deep Dive)")
                        self._refresh_display()
                        continue
                    if user_input in ("/c", "/clear"):
                        self._chat_history.clear()
                        self._refresh_display()
                        continue
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
                    # Use session thread_id for context memory
                    thread_id = self._session_thread_id
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
                            # Complete message - only print if we haven't streamed tokens
                            message = event.data.get("content", "") if hasattr(event, "data") else ""
                            if message and not full_response:
                                full_response = message
                                self.console.print(message)
                            elif message:
                                # Already streamed, just update full_response
                                full_response = message
                        elif event_type == StreamEventType.THINKING:
                            thought = event.data.get("content", "") if hasattr(event, "data") else ""
                            if thought:
                                self.console.print(f"[dim yellow]💭 {thought[:80]}...[/dim yellow]")
                        elif event_type == StreamEventType.INTERRUPT:
                            # HITL interrupt - prompt user for approval
                            data = event.data if hasattr(event, "data") else {}
                            hitl_approved = await self._handle_hitl(data, session)
                            if hitl_approved:
                                # Re-execute with yolo mode
                                self.console.print("[green]✅ Approved. Executing...[/green]")
                                retry_response = ""
                                async for retry_event in self.client.chat_stream(
                                    user_input, thread_id + "-approved", self.mode, yolo=True
                                ):
                                    retry_type = retry_event.type if hasattr(retry_event, "type") else None
                                    if retry_type == StreamEventType.TOKEN:
                                        token = retry_event.data.get("content", "") if hasattr(retry_event, "data") else ""
                                        retry_response += token
                                        self.console.print(token, end="")
                                    elif retry_type == StreamEventType.MESSAGE:
                                        message = retry_event.data.get("content", "") if hasattr(retry_event, "data") else ""
                                        if message and not retry_response:
                                            retry_response = message
                                            self.console.print(message)
                                        elif message:
                                            retry_response = message
                                full_response = retry_response
                            else:
                                full_response = "❌ Operation cancelled by user."
                                self.console.print(f"[yellow]{full_response}[/yellow]")
                            break

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

    async def run_repl(self) -> None:
        """Run in lightweight REPL mode (no screen refresh).

        A simpler interactive mode that doesn't clear the screen,
        suitable for terminal multiplexers and simple queries.
        """
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.styles import Style as PTStyle

        self.running = True

        style = PTStyle.from_dict({
            "prompt": "cyan bold",
        })
        session: PromptSession = PromptSession(style=style)

        try:
            while self.running:
                try:
                    user_input = await session.prompt_async(
                        HTML(f"<cyan><b>[{self.mode}] ❯ </b></cyan>"),
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
                    if user_input in ("/h", "/help"):
                        self.console.print("[cyan]Commands:[/cyan]")
                        self.console.print("  /h, /help     Show this help")
                        self.console.print("  /q, /exit     Exit REPL")
                        self.console.print("  /mode <m>     Switch mode (standard/expert)")
                        self.console.print("  /s            Switch to standard mode")
                        self.console.print("  /e            Switch to expert mode")
                        self.console.print("  /status       Show system status")
                        continue
                    if user_input == "/s":
                        self.mode = "standard"
                        self.console.print("[green]✅ Switched to Standard mode[/green]")
                        continue
                    if user_input == "/e":
                        self.mode = "expert"
                        self.console.print("[yellow]✅ Switched to Expert mode (Deep Dive)[/yellow]")
                        continue
                    if user_input.startswith("/mode "):
                        new_mode = user_input.split(" ", 1)[1].strip().lower()
                        if new_mode in ("standard", "expert"):
                            self.mode = new_mode
                            self.console.print(f"[green]✅ Switched to {self.mode} mode[/green]")
                        else:
                            self.console.print(f"[red]Unknown mode: {new_mode}. Use 'standard' or 'expert'.[/red]")
                        continue
                    if user_input in ("/status", "/st"):
                        await self._show_status_inline()
                        continue
                    self.console.print(f"[yellow]Unknown command: {user_input}. Type /h for help.[/yellow]")
                    continue

                # Print user input
                self.console.print(f"[bold green]You[/bold green]: {user_input}")
                self.console.print()

                # Show thinking indicator
                self.console.print("[yellow]💭 Thinking...[/yellow]")

                # Send query and stream response
                try:
                    thread_id = self._session_thread_id
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
                                self.console.print(token, end="")
                        elif event_type == StreamEventType.MESSAGE:
                            message = event.data.get("content", "") if hasattr(event, "data") else ""
                            if message and not full_response:
                                full_response = message
                                self.console.print(message)
                            elif message:
                                full_response = message
                        elif event_type == StreamEventType.THINKING:
                            thought = event.data.get("content", "") if hasattr(event, "data") else ""
                            if thought:
                                self.console.print(f"[dim yellow]💭 {thought[:80]}...[/dim yellow]")

                    # Add newline after streaming
                    if full_response:
                        self.console.print()
                        self.console.print()

                except Exception as e:
                    self.console.print(f"[red]Error: {e}[/red]")
                    self.console.print()

        except KeyboardInterrupt:
            pass

        self.console.print()
        self.console.print("[yellow]👋 REPL closed. Goodbye![/yellow]")

    async def run_batch(
        self,
        queries: list[str],
        yolo: bool = False,
        verbose: bool = False,
        debug: bool = False,
        json_output: bool = False,
    ) -> list[str]:
        """Run batch queries non-interactively (for testing/scripting).

        Args:
            queries: List of queries to execute sequentially
            yolo: If True, auto-approve HITL (skip interactive prompts)
            verbose: Show detailed output
            debug: Show debug information (LLM calls, tool timing)
            json_output: Output as JSON

        Returns:
            List of responses for each query
        """

        responses: list[str] = []
        all_debug_info: list[dict] = []

        if not json_output and self.show_banner:
            self._print_header()

        for i, query in enumerate(queries, 1):
            if not json_output:
                self.console.print(f"\n[cyan]━━━ Query {i}/{len(queries)} ━━━[/cyan]")
                self.console.print(f"[bold cyan]You:[/bold cyan] {query}")
            self.add_message("user", query)

            full_response = ""
            tool_calls: list[dict] = []
            thinking_steps: list[str] = []
            start_time = time.time()

            try:
                thread_id = self._session_thread_id

                # Use ThinkingTree for verbose mode
                if verbose and not json_output:
                    with ThinkingTree(self.console) as tree:
                        full_response, tool_calls, thinking_steps = await self._process_stream_with_tree(
                            query, thread_id, yolo, tree
                        )
                else:
                    # Simple mode - minimal output
                    if not json_output:
                        self.console.print("[yellow]💭 Thinking...[/yellow]")
                    full_response, tool_calls, thinking_steps = await self._process_stream_simple(
                        query, thread_id, yolo, json_output
                    )

                duration_ms = int((time.time() - start_time) * 1000)

                # Add newline after streaming
                if full_response and not json_output:
                    self.console.print()

                if full_response:
                    self.add_message("assistant", full_response.strip())
                    responses.append(full_response.strip())
                else:
                    self.add_message("assistant", "[No response]")
                    responses.append("[No response]")

                # Collect debug info
                if debug:
                    all_debug_info.append({
                        "query": query,
                        "duration_ms": duration_ms,
                        "tool_calls": tool_calls,
                        "thinking_steps": len(thinking_steps),
                    })
                    if not json_output:
                        debug_renderer = DebugRenderer(self.console)
                        debug_info = DebugInfo()
                        debug_info.tool_calls = tool_calls
                        debug_info.thinking_steps = thinking_steps
                        # Set start/end time to calculate duration_ms properly
                        debug_info.start_time = start_time
                        debug_info.end_time = time.time()
                        debug_renderer.render(debug_info)

            except Exception as e:
                error_msg = f"Error: {e}"
                self.add_message("assistant", error_msg)
                responses.append(error_msg)
                if not json_output:
                    self.console.print(f"[red]{error_msg}[/red]")

        if json_output:
            import json as json_lib
            output = {
                "queries": len(queries),
                "responses": responses,
            }
            if debug:
                output["debug"] = all_debug_info
            print(json_lib.dumps(output, ensure_ascii=False, indent=2))
        else:
            self.console.print(f"\n[green]✅ Batch complete: {len(responses)}/{len(queries)} queries processed[/green]")

        return responses

    async def _process_stream_with_tree(
        self,
        query: str,
        thread_id: str,
        yolo: bool,
        tree: ThinkingTree,
    ) -> tuple[str, list[dict], list[str]]:
        """Process stream events with ThinkingTree visualization."""
        from olav.cli.thin_client import StreamEventType

        full_response = ""
        tool_calls: list[dict] = []
        thinking_steps: list[str] = []
        thinking_started = False

        async for event in self.client.chat_stream(query, thread_id=thread_id, mode=self.mode, yolo=yolo):
            event_type = event.type if hasattr(event, "type") else None
            data = event.data if hasattr(event, "data") else {}

            if event_type == StreamEventType.THINKING:
                thinking = data.get("thinking", {})
                content = thinking.get("content", "") if isinstance(thinking, dict) else str(data.get("content", ""))
                if content:
                    tree.add_thinking(content)
                    thinking_steps.append(content)
                    thinking_started = True

            elif event_type == StreamEventType.TOOL_START:
                if thinking_started:
                    tree.finalize_thinking()
                    thinking_started = False
                tool_info = data.get("tool", {})
                if not tool_info:
                    tool_info = {"name": data.get("name", "unknown"), "args": data.get("args", {})}
                tree.add_tool_call(
                    tool_info.get("display_name") or tool_info.get("name", "unknown"),
                    tool_info.get("args", {}),
                )
                tool_calls.append(tool_info)

            elif event_type == StreamEventType.TOOL_END:
                tool_info = data.get("tool", {})
                if not tool_info:
                    tool_info = {"name": data.get("name", "unknown"), "success": data.get("success", True)}
                tree.mark_tool_complete(
                    tool_info.get("name", "unknown"),
                    success=tool_info.get("success", True),
                )
                # Update tool call with duration
                for tc in reversed(tool_calls):
                    if tc.get("name") == tool_info.get("name"):
                        tc["duration_ms"] = tool_info.get("duration_ms", 0)
                        tc["success"] = tool_info.get("success", True)
                        break

            elif event_type == StreamEventType.TOKEN:
                if thinking_started:
                    tree.finalize_thinking()
                    thinking_started = False
                token = data.get("content", "")
                if token:
                    full_response += token

            elif event_type == StreamEventType.MESSAGE:
                message = data.get("content", "")
                if (message and not full_response) or message:
                    full_response = message

            elif event_type == StreamEventType.INTERRUPT:
                if thinking_started:
                    tree.finalize_thinking()
                    thinking_started = False
                # Handle HITL in tree mode
                if yolo:
                    tree.tree.add("[yellow]⚠️ HITL auto-approved (yolo)[/yellow]")
                    retry_response = await self._execute_with_yolo(query, thread_id)
                    full_response = retry_response
                else:
                    tool_name = data.get("tool_name", "unknown")
                    tree.tree.add(f"[red]❌ HITL required: {tool_name} - use --yolo[/red]")
                    full_response = "❌ Operation cancelled - HITL required"
                break

        # Print the response after tree
        if full_response:
            result_renderer = ResultRenderer(self.console)
            result_renderer.render_message(full_response)

        return full_response, tool_calls, thinking_steps

    async def _process_stream_simple(
        self,
        query: str,
        thread_id: str,
        yolo: bool,
        json_output: bool = False,
    ) -> tuple[str, list[dict], list[str]]:
        """Process stream events with simple output (no ThinkingTree)."""
        from olav.cli.thin_client import StreamEventType

        full_response = ""
        tool_calls: list[dict] = []
        thinking_steps: list[str] = []

        async for event in self.client.chat_stream(query, thread_id=thread_id, mode=self.mode, yolo=yolo):
            event_type = event.type if hasattr(event, "type") else None
            data = event.data if hasattr(event, "data") else {}

            if event_type == StreamEventType.TOOL_START:
                tool_name = data.get("name", "tool")
                if not json_output:
                    self.console.print(f"[magenta]🔧 Calling {tool_name}...[/magenta]")
                tool_calls.append({"name": tool_name, "args": data.get("args", {})})

            elif event_type == StreamEventType.TOOL_END:
                tool_name = data.get("name", "tool")
                success = data.get("success", True)
                if not json_output:
                    icon = "✅" if success else "❌"
                    self.console.print(f"[magenta]{icon} {tool_name} completed[/magenta]")

            elif event_type == StreamEventType.TOKEN:
                token = data.get("content", "")
                if token:
                    full_response += token
                    if not json_output:
                        self.console.print(token, end="")

            elif event_type == StreamEventType.MESSAGE:
                message = data.get("content", "")
                if message and not full_response:
                    full_response = message
                    if not json_output:
                        self.console.print(message)
                elif message:
                    full_response = message

            elif event_type == StreamEventType.THINKING:
                content = data.get("content", "")
                if content:
                    thinking_steps.append(content)
                    if not json_output:
                        self.console.print(f"[dim yellow]💭 {content[:80]}...[/dim yellow]")

            elif event_type == StreamEventType.INTERRUPT:
                if yolo:
                    if not json_output:
                        self.console.print("[yellow]⚠️ HITL auto-approved (yolo)[/yellow]")
                    retry_response = await self._execute_with_yolo(query, thread_id)
                    full_response = retry_response
                else:
                    tool_name = data.get("tool_name", "unknown")
                    if not json_output:
                        self.console.print(f"[yellow]⚠️ HITL required: {tool_name}[/yellow]")
                        self.console.print("[red]❌ Rejected (use --yolo to auto-approve)[/red]")
                    full_response = "❌ Operation cancelled - HITL required"
                break

        return full_response, tool_calls, thinking_steps

    async def _execute_with_yolo(self, query: str, thread_id: str) -> str:
        """Re-execute query with yolo mode after HITL approval."""
        from olav.cli.thin_client import StreamEventType

        full_response = ""
        async for event in self.client.chat_stream(query, thread_id + "-approved", self.mode, yolo=True):
            event_type = event.type if hasattr(event, "type") else None
            data = event.data if hasattr(event, "data") else {}

            if event_type == StreamEventType.TOKEN:
                token = data.get("content", "")
                full_response += token
            elif event_type == StreamEventType.MESSAGE:
                message = data.get("content", "")
                if message:
                    full_response = message

        return full_response

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

    async def _handle_hitl(self, data: dict, session) -> bool:
        """Handle HITL interrupt in dashboard.

        Args:
            data: HITL event data containing tool_name, hitl_operation, etc.
                  OR config_plan from Device Execution Workflow
            session: PromptSession for user input

        Returns:
            True if approved, False if rejected
        """
        from rich.panel import Panel
        from rich.markdown import Markdown

        # Display HITL prompt
        self.console.print()
        self.console.print(Panel(
            "[bold yellow]⚠️  HITL Approval Required[/bold yellow]",
            title="Human-in-the-Loop",
            border_style="yellow",
        ))

        # Track impact to avoid misleading messaging.
        impact_message = "[bold]This operation will modify device configuration.[/bold]"

        # Check for Device Execution Workflow format (config_plan)
        config_plan = data.get("config_plan")
        execution_plan = data.get("execution_plan")
        workflow_type = data.get("workflow_type")
        
        if config_plan or execution_plan:
            # Device Execution Workflow format
            plan = config_plan or execution_plan
            
            self.console.print(f"\n[bold]Workflow:[/bold] [cyan]{workflow_type or 'device_execution'}[/cyan]")
            
            # Extract plan details
            if isinstance(plan, dict):
                # Show target device
                target = plan.get("target_device") or plan.get("device") or "unknown"
                self.console.print(f"[bold]Target Device:[/bold] [green]{target}[/green]")
                
                # Show operation type
                op_type = plan.get("operation_type") or plan.get("action") or "configuration change"
                self.console.print(f"[bold]Operation:[/bold] {op_type}")
                
                # Show interfaces if present
                interfaces = plan.get("interfaces") or plan.get("target_interfaces")
                if interfaces:
                    self.console.print(f"[bold]Interfaces:[/bold] {interfaces}")
                
                # Show complete plan as formatted content
                plan_md = plan.get("plan_markdown") or plan.get("plan") or plan.get("full_plan")
                if plan_md:
                    self.console.print("\n[bold]Configuration Plan:[/bold]")
                    self.console.print(Panel(Markdown(str(plan_md)), border_style="dim"))
                else:
                    # Show raw plan dict
                    import json
                    plan_str = json.dumps(plan, indent=2, ensure_ascii=False, default=str)
                    self.console.print("\n[bold]Configuration Plan:[/bold]")
                    self.console.print(Panel(plan_str, border_style="dim"))
            else:
                # Plan is just a string
                self.console.print("\n[bold]Configuration Plan:[/bold]")
                self.console.print(Panel(str(plan), border_style="dim"))
            
            # Show message if present
            message = data.get("message")
            if message:
                self.console.print(f"\n[dim]{message}[/dim]")

            impact_message = "[bold]This operation will modify device configuration.[/bold]"
        elif data.get("action") == "approval_required" and (
            data.get("api_endpoint") or data.get("operation_plan")
        ):
            # NetBox Management Workflow format
            api_endpoint = data.get("api_endpoint") or "unknown"
            operation_plan = data.get("operation_plan")

            self.console.print("\n[bold]Tool:[/bold] [cyan]NetBox API[/cyan]")
            self.console.print(f"[bold]Endpoint:[/bold] {api_endpoint}")

            method = None
            if isinstance(operation_plan, dict):
                method = operation_plan.get("method")
            if isinstance(method, str) and method.strip():
                method_u = method.strip().upper()
                self.console.print(f"[bold]Method:[/bold] {method_u}")
            else:
                method_u = None

            if operation_plan:
                import json

                plan_str = json.dumps(operation_plan, indent=2, ensure_ascii=False, default=str)
                self.console.print("\n[bold]Operation Plan:[/bold]")
                self.console.print(Panel(plan_str, border_style="dim"))

            # Defensive: if somehow a read-only NetBox op reached HITL, auto-continue.
            if method_u in ("GET", "HEAD", "OPTIONS"):
                self.console.print()
                self.console.print("[green]Read-only NetBox query detected; no approval required. Continuing...[/green]")
                return True

            impact_message = "[bold]This operation will modify NetBox data.[/bold]"
        else:
            # Standard Mode format (tool_name, hitl_operation, etc.)
            tool_name = data.get("tool_name", "unknown")
            operation = data.get("hitl_operation", "configuration change")
            parameters = data.get("hitl_parameters", {})

            # Show operation details
            self.console.print(f"\n[bold]Tool:[/bold] [cyan]{tool_name}[/cyan]")
            self.console.print(f"[bold]Operation:[/bold] {operation}")

            # Show device and command if available
            device = parameters.get("device") or parameters.get("hostname", "unknown") if parameters else "unknown"
            command = parameters.get("command", "") if parameters else ""

            self.console.print(f"[bold]Device:[/bold] [green]{device}[/green]")

            if command:
                self.console.print("\n[bold]Command to execute:[/bold]")
                self.console.print(Panel(command, border_style="dim"))

            impact_message = "[bold]This operation will modify device configuration.[/bold]"

        self.console.print()
        self.console.print(impact_message)
        self.console.print()

        # Prompt for approval using prompt_toolkit
        try:
            from prompt_toolkit.formatted_text import HTML
            response = await session.prompt_async(
                HTML("<yellow><b>Proceed? [y/N]: </b></yellow>"),
            )
            response = response.strip().lower()

            approved = response in ("y", "yes")
            self.add_message("user", f"HITL: {'approved' if approved else 'rejected'}")
            return approved
        except (EOFError, KeyboardInterrupt):
            self.console.print("\n[yellow]Cancelled.[/yellow]")
            return False


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
