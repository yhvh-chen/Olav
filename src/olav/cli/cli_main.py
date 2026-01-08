"""OLAV CLI Main Entry Point - Interactive CLI using prompt-toolkit."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

from olav.agent import create_olav_agent
from olav.cli.session import OlavPromptSession
from olav.cli.memory import AgentMemory
from olav.cli.commands import execute_command
from olav.cli.input_parser import parse_input
from olav.cli.display import display_banner, BannerType


def run_cli(
    memory: AgentMemory,
    session: OlavPromptSession,
    agent,
) -> None:
    """Run the OLAV CLI (synchronous main loop).
    
    Args:
        memory: Agent memory manager
        session: Prompt session
        agent: OLAV agent instance
    """
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
            
            # Invoke agent (async call wrapped in asyncio.run)
            print("🔍 Processing...", flush=True)
            try:
                result = asyncio.run(agent.ainvoke(
                    {
                        "messages": [
                            {"role": "user", "content": processed_text}
                        ]
                    }
                ))
                
                # Extract output from agent response
                # Agent returns {"messages": [HumanMessage, AIMessage, ...]}
                output = None
                if result and "messages" in result:
                    messages = result["messages"]
                    # Get the last AI message content
                    for msg in reversed(messages):
                        if hasattr(msg, "content") and hasattr(msg, "type"):
                            if msg.type == "ai":
                                output = msg.content
                                break
                        elif hasattr(msg, "content"):
                            # AIMessage has content attribute
                            output = msg.content
                            break
                elif result and "output" in result:
                    output = result["output"]
                
                if output:
                    print(f"\n{output}\n")
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


def main() -> None:
    """Main entry point for OLAV CLI."""
    import sys
    
    # Check if running in interactive mode
    is_interactive = sys.stdin.isatty()
    
    try:
        # Display welcome message
        print("\n" + "=" * 60)
        print("💬 OLAV Interactive CLI - v0.8 Phase 6")
        print("=" * 60)
        print("Starting up...\n")

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
                multiline=False,  # Single Enter to submit
            )
        except Exception as e:
            print(f"⚠️  Warning: Could not initialize interactive features: {e}")
            print("   Falling back to basic input mode.\n")
            # Create a basic session with fallback
            session = OlavPromptSession(
                history_file=".olav/.cli_history",
                enable_completion=False,
                enable_history=False,
                multiline=False,
            )

        # Display banner - only use Rich in interactive mode
        if is_interactive:
            display_banner(BannerType.SNOWMAN)
        else:
            # Simple text banner for piped mode
            print("  ⛄ OLAV v0.8 - Network Operations AI Assistant\n")
            print("  Type /help for available commands or just ask a question.\n")

        # Create agent
        agent = create_olav_agent(
            enable_skill_routing=True,
            enable_subagents=True,
            debug=False,
        )

        # Run CLI (synchronous loop - prompt-toolkit manages its own event loop)
        run_cli(memory, session, agent)

        # Save memory before exit
        memory.save()

    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
