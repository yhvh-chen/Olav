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


async def stream_agent_response(
    agent: Any, 
    messages: list[dict], 
    verbose: bool = False,
    memory: "AgentMemory | None" = None,
) -> str:
    """Stream agent response with hierarchical output display.

    P8 Enhancement: Added layered streaming with tool call visibility and
    structured output. Supports verbose mode for debugging.

    Displays in compact mode (default):
    - Tool calls: Highlighted panels showing device/command
    - Results: Standard formatted output
    - Progress: Spinner while LLM is thinking (if display_thinking enabled)

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
    from config.settings import settings
    from olav.cli.display import StreamingDisplay

    # Use display_thinking config - if true, show streaming tokens
    show_thinking = settings.display_thinking or verbose
    # Enable streaming display when display_thinking is on
    stream_tokens = show_thinking
    display = StreamingDisplay(verbose=stream_tokens, show_spinner=not stream_tokens)

    full_response = ""
    accumulated_content = ""
    previous_tool = None
    displayed_tool_types: set[str] = set()  # Track displayed tool types
    first_content_seen = False
    spinner_started = False

    # Tools that deserve full panel display
    IMPORTANT_TOOLS = {"nornir_execute", "smart_query", "api_call"}

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

    # Stream tokens as they arrive - use stream_mode="messages" for token-level streaming
    # "messages" mode provides incremental token updates (real streaming)
    event_count = 0
    accumulated_content = ""

    async for chunk in agent.astream({"messages": messages}, stream_mode="messages"):
        event_count += 1

        # messages mode returns (message, metadata) tuples
        if isinstance(chunk, tuple) and len(chunk) >= 1:
            msg = chunk[0]  # First element is the message
            msg_type = type(msg).__name__

            # Handle tool calls (AIMessage/AIMessageChunk with tool_calls)
            if msg_type in ("AIMessage", "AIMessageChunk") and hasattr(msg, "tool_calls"):
                if msg.tool_calls:
                    # Stop spinner before showing tool calls
                    if spinner_started:
                        display.stop_processing_status()
                        spinner_started = False
                    
                    for tool_call in msg.tool_calls:
                        # Avoid duplicate display of same tool call
                        tool_id = getattr(tool_call, "id", "") or tool_call.get("id")
                        if tool_id == previous_tool:
                            continue

                        parsed = parse_tool_call(tool_call)
                        if parsed:
                            tool_name, device, command = parsed
                            
                            # Important tools get full panel
                            if tool_name in IMPORTANT_TOOLS:
                                display.show_tool_call(
                                    tool_name=tool_name,
                                    device=device,
                                    command=command,
                                    status="executing",
                                )
                            else:
                                # Other tools: show compact, but only first time per type
                                if tool_name not in displayed_tool_types:
                                    display.show_tool_call(
                                        tool_name=tool_name,
                                        device=device,
                                        command=command,
                                        status="executing",
                                        compact=True,
                                    )
                                    displayed_tool_types.add(tool_name)
                            
                            previous_tool = tool_id

            # Handle AI response content - stream it token by token
            if msg_type in ("AIMessage", "AIMessageChunk") and hasattr(msg, "content"):
                content_chunk = msg.content
                # Accept empty strings too (they still count as chunks)
                if content_chunk is not None:
                    # This is a delta token from the LLM
                    if not first_content_seen and content_chunk:
                        first_content_seen = True
                        # Only show spinner in compact mode (non-streaming)
                        if not spinner_started and not stream_tokens:
                            display.show_processing_status("🤔 Thinking...")
                            spinner_started = True

                    # Accumulate and display content deltas
                    if content_chunk:
                        accumulated_content += content_chunk
                    
                        if stream_tokens:
                            # Stream mode: show each token as it arrives
                            display.show_thinking(content_chunk, end="")
                        elif spinner_started:
                            # Compact mode with spinner, just accumulate for now
                            pass
                        else:
                            # Compact mode without spinner, stream directly
                            display.show_result(content_chunk, end="")

    # Stop spinner if still running
    if spinner_started:
        display.stop_processing_status()
        # In compact mode with spinner, show accumulated result with Markdown
        if accumulated_content.strip():
            display.show_result(accumulated_content, markdown=True)
    elif stream_tokens and accumulated_content.strip():
        # After streaming tokens, just add newline (content already shown)
        display.show_result("\n")
    elif accumulated_content.strip():
        # Compact mode without streaming, show with Markdown
        display.show_result(accumulated_content, markdown=True)

    full_response = accumulated_content

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
    from config.settings import settings
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
                # Build messages with conversation history
                history = memory.get_conversation_messages(max_turns=10, max_chars=8000)
                # Format: history + current message
                messages = list(history) + [("user", processed_text)]
                
                # Use verbose mode only if DISPLAY_THINKING=true
                use_verbose = settings.display_thinking
                output = asyncio.run(stream_agent_response(
                    agent, messages, verbose=use_verbose, memory=memory
                ))

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
