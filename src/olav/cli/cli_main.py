"""OLAV CLI Main Entry Point - Typer-based CLI with interactive mode.

P7 Enhancement: Added streaming output for real-time token display.
Supports:
  - uv run olav              # Interactive mode (default)
  - uv run olav query "..."  # Single query
  - uv run olav devices      # List devices
  - uv run olav --help       # Show help
"""

import asyncio
import sys
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from olav.cli.memory import AgentMemory
    from olav.cli.session import OlavPromptSession

# Lazy imports to speed up --help
console = Console()
app = typer.Typer(
    name="olav",
    help="OLAV v0.8 - Network Operations AI Assistant",
    no_args_is_help=False,  # Default to interactive mode
    invoke_without_command=True,
)


async def stream_agent_response(agent: Any, messages: list[dict], verbose: bool = False) -> str:
    """Stream agent response with hierarchical output display.

    P8 Enhancement: Added layered streaming with tool call visibility and
    structured output. Supports verbose mode for debugging.

    Displays in compact mode (default):
    - Tool calls: Highlighted panels showing device/command
    - Results: Standard formatted output
    - Progress: Spinner while LLM is thinking

    Displays in verbose mode (--verbose flag):
    - Full LLM thinking process as it streams
    - Tool calls with execution status
    - Final results with full context

    Args:
        agent: OLAV agent instance
        messages: Conversation messages
        verbose: If True, show full thinking process; else show tools + results only

    Returns:
        Complete response text (final result only)
    """
    from olav.cli.display import StreamingDisplay

    display = StreamingDisplay(verbose=verbose, show_spinner=True)

    full_response = ""
    current_content = ""
    previous_tool = None
    first_content_seen = False
    spinner_started = False

    def extract_ai_content(msg: Any) -> str:
        """Extract content from AIMessage, ignoring tool calls."""
        if hasattr(msg, "content") and msg.content:
            if hasattr(msg, "tool_calls") and msg.tool_calls and not msg.content:
                return ""
            return msg.content
        return ""

    def parse_tool_call(tool_call: Any) -> tuple[str, str, str] | None:
        """Parse tool call to extract name, device, and command.

        Args:
            tool_call: Tool call object from AIMessage

        Returns:
            Tuple of (tool_name, device, command) or None if not parseable
        """
        try:
            name = getattr(tool_call, "name", "") or tool_call.get("name", "")
            if not name:
                return None

            # Extract device and command from args
            args = getattr(tool_call, "args", {}) or tool_call.get("args", {})
            if isinstance(args, str):
                # Try to parse if it's a JSON string
                import json

                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}

            device = args.get("device") or args.get("target")
            command = args.get("command")

            return (name, device, command)
        except (AttributeError, TypeError):
            return None

    # Stream tokens as they arrive - try stream_mode="updates" for real-time tokens
    # If not available, fall back to stream_mode="values"
    try:
        stream_mode = "updates"
        async for event in agent.astream({"messages": messages}, stream_mode=stream_mode):
            # Handle 'messages' updates (delta tokens from LLM)
            if "messages" in event:
                msgs = event["messages"]
                if msgs:
                    last_msg = msgs[-1]
                    msg_type = type(last_msg).__name__

                    # Handle tool calls (AIMessage with tool_calls)
                    if msg_type == "AIMessage" and hasattr(last_msg, "tool_calls"):
                        if last_msg.tool_calls:
                            # Stop spinner before showing tool calls
                            if spinner_started and not verbose:
                                display.stop_processing_status()
                                spinner_started = False

                            for tool_call in last_msg.tool_calls:
                                # Avoid duplicate display of same tool
                                tool_id = getattr(tool_call, "id", "") or tool_call.get("id")
                                if tool_id == previous_tool:
                                    continue

                                parsed = parse_tool_call(tool_call)
                                if parsed:
                                    tool_name, device, command = parsed
                                    display.show_tool_call(
                                        tool_name=tool_name,
                                        device=device,
                                        command=command,
                                        status="executing",
                                    )
                                    previous_tool = tool_id

                    # Handle AI response content - stream it in real-time
                    if msg_type == "AIMessage":
                        new_content = extract_ai_content(last_msg)
                        if new_content and new_content != current_content:
                            # Stream only new characters (delta)
                            delta = new_content[len(current_content) :]

                            # Start spinner on first content in compact mode
                            if not first_content_seen and not verbose and delta.strip():
                                first_content_seen = True
                                if not spinner_started:
                                    display.show_processing_status(
                                        "🤔 Thinking...", show_spinner=True
                                    )
                                    spinner_started = True

                            if verbose and delta.strip():
                                # In verbose mode, show thinking as it arrives
                                display.show_thinking(delta, end="")
                            elif not verbose and delta.strip():
                                # In compact mode, show final result (buffer in spinner)
                                pass  # Keep spinner showing while thinking

                            current_content = new_content
    except Exception:
        # Fall back to values mode if updates not supported
        async for event in agent.astream({"messages": messages}, stream_mode="values"):
            # Handle 'messages' list in values stream
            if "messages" in event:
                msgs = event["messages"]
                # Check the last message for AI response
                if msgs:
                    last_msg = msgs[-1]
                    msg_type = type(last_msg).__name__

                    # Handle tool calls (AIMessage with tool_calls)
                    if msg_type == "AIMessage" and hasattr(last_msg, "tool_calls"):
                        if last_msg.tool_calls:
                            # Stop spinner before showing tool calls
                            if spinner_started and not verbose:
                                display.stop_processing_status()
                                spinner_started = False

                            for tool_call in last_msg.tool_calls:
                                # Avoid duplicate display of same tool
                                tool_id = getattr(tool_call, "id", "") or tool_call.get("id")
                                if tool_id == previous_tool:
                                    continue

                                parsed = parse_tool_call(tool_call)
                                if parsed:
                                    tool_name, device, command = parsed
                                    display.show_tool_call(
                                        tool_name=tool_name,
                                        device=device,
                                        command=command,
                                        status="executing",
                                    )
                                    previous_tool = tool_id

                    # Handle final AI response (text content)
                    if msg_type == "AIMessage":
                        new_content = extract_ai_content(last_msg)
                        if new_content and new_content != current_content:
                            # Start spinner on first content in compact mode
                            if not first_content_seen and not verbose and new_content.strip():
                                first_content_seen = True
                                if not spinner_started:
                                    display.show_processing_status(
                                        "🤔 Thinking...", show_spinner=True
                                    )
                                    spinner_started = True

                            # Stream only new characters (delta)
                            delta = new_content[len(current_content) :]
                            if verbose and delta.strip():
                                # In verbose mode, show all content
                                display.show_thinking(delta, end="")
                            # In compact mode, buffer content until tool calls
                            current_content = new_content

    # Stop spinner if still running
    if spinner_started:
        display.stop_processing_status()

    # Display final result
    if current_content and current_content.strip():
        display.show_result(current_content, end="\n")

    full_response = current_content

    return full_response


def run_interactive_loop(
    memory: "AgentMemory",
    session: "OlavPromptSession",
    agent: Any,
) -> None:
    """Run the OLAV CLI (synchronous main loop).

    Args:
        memory: Agent memory manager
        session: Prompt session
        agent: OLAV agent instance
    """
    from olav.cli.commands import execute_command
    from olav.cli.input_parser import parse_input

    print("Type /help for available commands or just ask a question.\n")

    while True:
        try:
            # Get user input (synchronous - prompt-toolkit handles its own event loop)
            user_input = session.prompt_sync("OLAV> ")

            # Strip BOM and whitespace (PowerShell on Windows adds BOM to piped input)
            user_input = user_input.lstrip("\ufeff").strip()

            if not user_input:
                continue

            # Check for slash commands first
            if user_input.startswith("/"):
                try:
                    # Run async command handler synchronously
                    result = asyncio.run(
                        execute_command(
                            user_input,
                            agent=agent,
                            memory=memory,
                        )
                    )
                    if result:
                        print(result)
                except EOFError:
                    # /quit raises EOFError - re-raise to exit
                    raise
                except Exception as e:
                    print(f"❌ Error: {e}", file=sys.stderr)
                continue

            # Parse input for special syntax (file refs, shell commands)
            processed_text, is_shell_cmd, shell_cmd = parse_input(user_input)

            # Handle shell commands
            if is_shell_cmd and shell_cmd:
                import subprocess

                try:
                    result = subprocess.run(
                        shell_cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.stdout:
                        print(result.stdout)
                    if result.stderr:
                        print(f"⚠️ {result.stderr}", file=sys.stderr)
                except subprocess.TimeoutExpired:
                    print("⏱️ Command timed out (30s)")
                except Exception as e:
                    print(f"❌ Error executing command: {e}")
                continue

            # Handle normal queries
            # Store in memory
            memory.add("user", processed_text)

            # P8: Stream agent response with layered output
            print("🔍 Processing...", flush=True)
            try:
                messages = [{"role": "user", "content": processed_text}]
                # Default to non-verbose in interactive mode for cleaner output
                output = asyncio.run(stream_agent_response(agent, messages, verbose=False))

                if output:
                    memory.add("assistant", output)
                else:
                    print("\n⚠️ No response from agent\n")

            except Exception as e:
                print(f"❌ Error: {str(e)}")

        except EOFError:
            # User pressed Ctrl+D or /quit
            print("\n👋 Goodbye! Session saved.")
            break
        except KeyboardInterrupt:
            print("\n⚠️ Interrupted. Type /quit to exit.")
            continue
        except Exception:
            # Suppress error printing to prevent infinite loops
            continue


@app.command()
def query(
    query_text: str = typer.Argument(..., help="Network operation query"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full LLM thinking process"),
) -> None:
    """Execute a single network operations query.

    Examples:
        olav query "查看 R1 的接口状态"
        olav query "R1 的 BGP 邻居" --debug
        olav query "Check R2 BGP" --verbose
    """
    from olav.agent import create_olav_agent

    console.print(Panel(f"[bold cyan]Query[/bold cyan]: {query_text}", border_style="cyan"))

    try:
        agent = create_olav_agent(debug=debug)
        messages = [{"role": "user", "content": query_text}]

        console.print("[dim]🔍 Processing...[/dim]")
        output = asyncio.run(stream_agent_response(agent, messages, verbose=verbose))

        if not output:
            console.print("[yellow]No response received[/yellow]")

    except Exception as e:
        console.print(f"[bold red]❌ Error: {str(e)}[/bold red]")
        if debug:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1) from None


@app.command()
def devices() -> None:
    """List all managed network devices."""
    from olav.tools.network import list_devices as nornir_list_devices

    console.print("[bold cyan]Loading network devices...[/bold cyan]")
    try:
        result = nornir_list_devices.invoke({})
        console.print(
            Panel(result, title="[bold cyan]Network Devices[/bold cyan]", border_style="cyan")
        )
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(1) from None


@app.command()
def version() -> None:
    """Show OLAV version and information."""
    console.print(
        Panel(
            "[bold cyan]OLAV v0.8[/bold cyan]\n"
            "Network Operations AI Assistant\n"
            "Powered by DeepAgents + LangChain",
            border_style="cyan",
        )
    )


@app.callback(invoke_without_command=True)
def interactive_mode(ctx: typer.Context) -> None:
    """Start interactive OLAV session (default when no command given)."""
    # If a subcommand was invoked, skip interactive mode
    if ctx.invoked_subcommand is not None:
        return

    # Import heavy modules only when needed
    from olav.agent import create_olav_agent
    from olav.cli.display import display_banner, load_banner_from_config
    from olav.cli.memory import AgentMemory
    from olav.cli.session import OlavPromptSession

    is_interactive = sys.stdin.isatty()

    try:
        console.print("\n" + "=" * 60)
        console.print("💬 OLAV Interactive CLI - v0.8")
        console.print("=" * 60 + "\n")

        # Create memory manager
        from pathlib import Path

        from config.settings import settings

        memory_file = str(Path(settings.agent_dir) / ".agent_memory.json")
        history_file = str(Path(settings.agent_dir) / ".cli_history")

        memory = AgentMemory(
            max_messages=100,
            memory_file=memory_file,
        )

        # Create CLI session
        try:
            session = OlavPromptSession(
                history_file=history_file,
                enable_completion=is_interactive,
                enable_history=is_interactive,
                multiline=False,
            )
        except Exception as e:
            console.print(f"[yellow]⚠️ Warning: {e}[/yellow]")
            session = OlavPromptSession(
                history_file=history_file,
                enable_completion=False,
                enable_history=False,
                multiline=False,
            )

        # Display banner
        if is_interactive:
            banner_text = load_banner_from_config()
            if banner_text:
                display_banner(banner_text)

        # Create agent
        agent = create_olav_agent(
            enable_skill_routing=True,
            enable_subagents=True,
            debug=False,
        )

        # Run interactive loop
        run_interactive_loop(memory, session, agent)
        memory.save()

    except KeyboardInterrupt:
        console.print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]❌ Fatal error: {e}[/bold red]")
        raise typer.Exit(1) from None


def main() -> None:
    """Main entry point for OLAV CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
