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
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Lazy imports to speed up --help
console = Console()
app = typer.Typer(
    name="olav",
    help="OLAV v0.8 - Network Operations AI Assistant",
    no_args_is_help=False,  # Default to interactive mode
    invoke_without_command=True,
)


async def stream_agent_response(agent, messages: list[dict]) -> str:
    """Stream agent response with real-time token output.
    
    P7 Enhancement: Reduces perceived latency by showing tokens as generated.
    
    Args:
        agent: OLAV agent instance
        messages: Conversation messages
        
    Returns:
        Complete response text
    """
    full_response = ""
    current_content = ""
    
    # Stream tokens as they arrive
    async for event in agent.astream({"messages": messages}):
        # Handle 'agent' events from LangGraph
        if "agent" in event:
            agent_output = event.get("agent", {})
            if "messages" in agent_output:
                for msg in agent_output["messages"]:
                    if hasattr(msg, "content") and msg.content:
                        new_content = msg.content
                        if new_content and new_content != current_content:
                            # Print only new characters (delta)
                            delta = new_content[len(current_content):]
                            print(delta, end="", flush=True)
                            current_content = new_content
        
        # Handle direct 'messages' in event (alternative format)
        if "messages" in event and "agent" not in event:
            for msg in event["messages"]:
                if hasattr(msg, "content") and msg.content:
                    new_content = msg.content
                    if new_content and new_content != current_content:
                        delta = new_content[len(current_content):]
                        print(delta, end="", flush=True)
                        current_content = new_content
    
    # Final newline
    print()
    full_response = current_content
    
    return full_response


def run_interactive_loop(
    memory: "AgentMemory",
    session: "OlavPromptSession",
    agent,
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
            user_input = user_input.lstrip('\ufeff').strip()
            
            if not user_input:
                continue

            # Check for slash commands first
            if user_input.startswith("/"):
                try:
                    # Run async command handler synchronously
                    result = asyncio.run(execute_command(
                        user_input,
                        agent=agent,
                        memory=memory,
                    ))
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
            
            # P7: Stream agent response for real-time output
            print("🔍 Processing...", flush=True)
            try:
                messages = [{"role": "user", "content": processed_text}]
                output = asyncio.run(stream_agent_response(agent, messages))
                
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
) -> None:
    """Execute a single network operations query.
    
    Examples:
        olav query "查看 R1 的接口状态"
        olav query "R1 的 BGP 邻居" --debug
    """
    from olav.agent import create_olav_agent
    
    console.print(Panel(f"[bold cyan]Query[/bold cyan]: {query_text}", border_style="cyan"))
    
    try:
        agent = create_olav_agent(debug=debug)
        messages = [{"role": "user", "content": query_text}]
        
        console.print("[dim]🔍 Processing...[/dim]")
        output = asyncio.run(stream_agent_response(agent, messages))
        
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
        console.print(Panel(result, title="[bold cyan]Network Devices[/bold cyan]", border_style="cyan"))
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(1) from None


@app.command()
def version() -> None:
    """Show OLAV version and information."""
    console.print(Panel(
        "[bold cyan]OLAV v0.8[/bold cyan]\n"
        "Network Operations AI Assistant\n"
        "Powered by DeepAgents + LangChain",
        border_style="cyan",
    ))


@app.callback(invoke_without_command=True)
def interactive_mode(ctx: typer.Context) -> None:
    """Start interactive OLAV session (default when no command given)."""
    # If a subcommand was invoked, skip interactive mode
    if ctx.invoked_subcommand is not None:
        return
    
    # Import heavy modules only when needed
    from olav.agent import create_olav_agent
    from olav.cli.session import OlavPromptSession
    from olav.cli.memory import AgentMemory
    from olav.cli.display import display_banner, BannerType
    
    is_interactive = sys.stdin.isatty()
    
    try:
        console.print("\n" + "=" * 60)
        console.print("💬 OLAV Interactive CLI - v0.8")
        console.print("=" * 60 + "\n")

        # Create memory manager
        memory = AgentMemory(
            max_messages=100,
            memory_file=".olav/.agent_memory.json",
        )

        # Create CLI session
        try:
            session = OlavPromptSession(
                history_file=".olav/.cli_history",
                enable_completion=is_interactive,
                enable_history=is_interactive,
                multiline=False,
            )
        except Exception as e:
            console.print(f"[yellow]⚠️ Warning: {e}[/yellow]")
            session = OlavPromptSession(
                history_file=".olav/.cli_history",
                enable_completion=False,
                enable_history=False,
                multiline=False,
            )

        # Display banner
        if is_interactive:
            display_banner(BannerType.SNOWMAN)

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
