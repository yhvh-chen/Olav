"""OLAV CLI - Enterprise Network Operations ChatOps Platform."""

import asyncio
import logging
import json
from pathlib import Path
import selectors
import sys
import time
from typing import Any

import typer
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from olav import __version__
# Agent imports moved to runtime (dynamic import based on --agent-mode)
from olav.tools.suzieq_tool import suzieq_query  # Direct tool access for one-shot timing
from olav.core.settings import settings
from olav.core.logging_config import setup_logging
from olav.ui import ChatUI
from config.settings import AgentConfig

logger = logging.getLogger("olav.main")
console = Console()

# Whitelist file path (persist approved write operations/commands)
WHITELIST_PATH = Path(__file__).resolve().parents[2] / "config" / "cli_whitelist.yaml"

def _load_whitelist() -> set[str]:
    if not WHITELIST_PATH.exists():
        return set()
    try:
        data = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
        items = data.get("approved", []) if isinstance(data, dict) else []
        return {str(i) for i in items}
    except Exception:
        return set()

def _persist_whitelist(items: set[str]) -> None:
    payload = {"approved": sorted(items)}
    WHITELIST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

app = typer.Typer(
    name="olav",
    help="OLAV - Omni-Layer Autonomous Verifier: Enterprise Network Operations ChatOps Platform",
    add_completion=False,
)


@app.command()
def chat(
    query: str | None = typer.Argument(None, help="Single query to execute (non-interactive mode)"),
    thread_id: str | None = typer.Option(None, help="Conversation thread ID (for resuming sessions)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed logs and timestamps"),
    agent_mode: str = typer.Option("react", "--agent-mode", "-m", help="Agent architecture: 'react' (new, fast) or 'legacy' (DeepAgents SubAgent)"),
) -> None:
    """Start interactive chat session with OLAV agent.
    
    Agent Modes:
        react: New ReAct architecture (Reasoning + Acting, 64% faster)
        legacy: Original DeepAgents SubAgent architecture (for comparison)
    
    Examples:
        # Interactive mode (ReAct)
        olav chat
        
        # Single query mode (ReAct)
        olav chat "查询设备 R1 的接口状态"
        
        # Use legacy architecture
        olav chat --agent-mode legacy
        
        # Verbose mode (show detailed logs)
        olav chat "查询 R1" --verbose
        
        # Resume previous conversation
        olav chat --thread-id "session-123"
    """
    # Setup logging first
    setup_logging(verbose)
    
    console.print(f"[bold green]OLAV v{__version__}[/bold green] - Network Operations ChatOps")
    console.print(f"LLM: {settings.llm_provider} ({settings.llm_model_name})")
    console.print(f"Agent: {agent_mode.upper()} {'(new)' if agent_mode == 'react' else '(legacy)'}")
    console.print(f"HITL: {'Enabled' if AgentConfig.ENABLE_HITL else 'Disabled'}")
    
    # Windows: Use SelectorEventLoop for psycopg async compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    if query:
        # Single query mode (non-interactive)
        asyncio.run(_run_single_query(query, thread_id, agent_mode))
    else:
        # Interactive chat mode
        console.print("\nType 'exit' or 'quit' to end session")
        console.print("Type 'help' for available commands\n")
        asyncio.run(_run_interactive_chat(thread_id, agent_mode))


async def _run_single_query(query: str, thread_id: str | None = None, agent_mode: str = "react") -> None:
    """Execute single query and exit.
    
    Args:
        query: User query to execute
        thread_id: Optional thread ID for conversation context
        agent_mode: Agent architecture ('react' or 'legacy')
    """
    ui = ChatUI(console)
    
    try:
        # Import appropriate agent based on mode
        if agent_mode == "react":
            from olav.agents.root_agent_react import create_root_agent_react
            agent, checkpointer_ctx = await create_root_agent_react()
        else:  # legacy
            from olav.agents.root_agent_legacy import create_root_agent
            agent, checkpointer_ctx = await create_root_agent()
        
        logger.debug(f"Root agent ({agent_mode}) initialized successfully")
        
        # Generate thread ID if not provided
        if not thread_id:
            import time
            thread_id = f"cli-single-{int(time.time())}"
        
        config = {"configurable": {"thread_id": thread_id}}
        
        # Show user query
        console.print()
        ui.show_user_message(query)
        
        # Stream response with thinking visualization
        result = await _stream_agent_response(
            agent=agent,
            query=query,
            config=config,
            ui=ui,
        )
        
        # Display final response
        if result["content"]:
            ui.show_agent_response(
                result["content"],
                metadata={
                    "tools_used": result.get("tools_used", []),
                    "data_source": result.get("data_source"),
                    "timings": result.get("timings", []),
                }
            )
        else:
            ui.show_warning("未收到 Agent 响应")
        
        # Cleanup checkpointer
        await checkpointer_ctx.__aexit__(None, None, None)
            
    except KeyboardInterrupt:
        ui.show_warning("查询已中断")
    except Exception as e:
        logger.error(f"Failed to execute query: {e}", exc_info=True)
        ui.show_error(str(e))
        raise typer.Exit(1)


async def _stream_agent_response(
    agent: Any,
    query: str,
    config: dict,
    ui: ChatUI,
) -> dict[str, Any]:
    """Stream agent response with thinking process visualization.
    
    Args:
        agent: Agent instance
        query: User query
        config: LangGraph config
        ui: ChatUI instance
        
    Returns:
        Dict with 'content', 'tools_used', and 'data_source'
    """
    response_content = ""
    tools_used = []
    tool_timings: list[dict[str, Any]] = []
    thinking_tree = ui.create_thinking_tree()
    current_nodes = {}  # Map tool call IDs to tree nodes
    tool_start_times = {}  # Map tool call IDs to start timestamps
    
    hitl_enabled = AgentConfig.ENABLE_HITL
    # Tools requiring HITL approval before execution (write/sensitive ops)
    hitl_required_tools = {"cli_tool", "netconf_tool", "nornir_tool", "netbox_api_call"}
    whitelist = _load_whitelist()

    with ui.create_thinking_context() as live:
        seen_tool_ids = set()  # Track processed tool calls
        
        async for chunk in agent.astream(
            {"messages": [HumanMessage(content=query)]},
            config=config,
            stream_mode="values"  # Get full state each update
        ):
            if not isinstance(chunk, dict) or "messages" not in chunk:
                continue
            
            messages = chunk["messages"]
            if not isinstance(messages, list):
                continue
            
            # Process only recent messages (last 10 to catch SubAgent internal calls)
            for msg in messages[-10:]:
                # Detect tool calls
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.get("name")
                        tool_args = tool_call.get("args", {})
                        tool_id = tool_call.get("id")

                        if tool_name and tool_id and tool_id not in seen_tool_ids:
                            seen_tool_ids.add(tool_id)
                            
                            # For SubAgent task wrapper, map to actual tool names
                            display_tool_name = tool_name
                            if tool_name == "task" and isinstance(tool_args, dict):
                                # Use subagent_type to determine tool category
                                subagent_type = tool_args.get("subagent_type", "")
                                description = tool_args.get("description", "").lower()
                                
                                # Map SubAgent types to actual tool names (matching ChatUI tool_names)
                                if subagent_type == "suzieq-analyzer":
                                    # Infer specific tool from description
                                    if any(kw in description for kw in ["schema", "字段", "表结构", "available", "fields"]):
                                        display_tool_name = "suzieq_schema_search"
                                    else:
                                        display_tool_name = "suzieq_query"
                                elif subagent_type == "netconf-executor":
                                    display_tool_name = "netconf_tool"
                                elif subagent_type == "rag-helper":
                                    display_tool_name = "rag_search"
                                else:
                                    # Keep subagent_type as fallback
                                    display_tool_name = subagent_type if subagent_type else tool_name
                            
                            # Determine if this invocation is potentially write/high-risk
                            requires_gate = False
                            risk_note = "read"
                            op_lower = json.dumps(tool_args, ensure_ascii=False).lower()
                            if tool_name == "netconf_tool" and "edit-config" in op_lower:
                                requires_gate = True
                                risk_note = "netconf-edit"
                            elif tool_name == "cli_tool" and "config_commands" in op_lower:
                                requires_gate = True
                                risk_note = "cli-config"
                            elif tool_name == "netbox_api_call" and any(tag in op_lower for tag in ["\"method\":\"post\"", "\"method\":\"put\"", "\"method\":\"patch\"", "\"method\":\"delete\""]):
                                requires_gate = True
                                risk_note = "netbox-write"

                            # Whitelist bypass
                            signature = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, ensure_ascii=False)}"
                            if signature in whitelist:
                                requires_gate = False
                                risk_note += " (whitelisted)"

                            if hitl_enabled and tool_name in hitl_required_tools and requires_gate:
                                console.print("\n[bold yellow]🔔 HITL 审批请求[/bold yellow]")
                                console.print(f"工具: [cyan]{tool_name}[/cyan]")
                                console.print(f"风险类型: [magenta]{risk_note}[/magenta]")
                                console.print(f"参数: [dim]{tool_args}[/dim]")
                                console.print("策略: 批准将此签名加入白名单 (后续免审批)")
                                decision = input("批准此操作? [Y/n/i(详情)]: ").strip().lower()
                                if decision == "i":
                                    console.print("\n[bold]详细参数 (JSON):[/bold]")
                                    try:
                                        console.print(json.dumps(tool_args, indent=2, ensure_ascii=False))
                                    except Exception:
                                        console.print(str(tool_args))
                                    decision = input("批准此操作? [Y/n]: ").strip().lower()
                                if decision in {"n", "no"}:
                                    console.print("[red]❌ 操作已拒绝，终止执行流[/red]")
                                    return {
                                        "content": "操作被人工拒绝，已安全中止。",
                                        "tools_used": tools_used,
                                        "data_source": None,
                                        "timings": tool_timings,
                                    }
                                else:
                                    console.print("[green]✅ 已批准，加入白名单并继续...[/green]")
                                    whitelist.add(signature)
                                    try:
                                        _persist_whitelist(whitelist)
                                    except Exception as pw_err:
                                        logger.warning(f"Failed to persist whitelist: {pw_err}")

                            # Add tool node after approval
                            node = ui.add_tool_call(thinking_tree, display_tool_name, tool_args)
                            current_nodes[tool_id] = (node, display_tool_name)  # Store display name
                            tool_start_times[tool_id] = time.perf_counter()
                            tools_used.append(display_tool_name)
                            live.update(thinking_tree)
                
                # Detect tool responses
                elif isinstance(msg, ToolMessage):
                    tool_id = getattr(msg, "tool_call_id", None)
                    if tool_id and tool_id in current_nodes:
                        node, tool_name = current_nodes[tool_id]  # tool_name is already the display name
                        ui.mark_tool_complete(node, tool_name, success=True)
                        
                        # Calculate elapsed time
                        if tool_id in tool_start_times:
                            elapsed = time.perf_counter() - tool_start_times[tool_id]
                            tool_timings.append({
                                "tool": tool_name,
                                "elapsed_sec": elapsed,
                            })
                        
                        live.update(thinking_tree)
                
                # Capture AI response content
                elif isinstance(msg, AIMessage) and hasattr(msg, "content") and msg.content:
                    # Only capture if no tool calls (final response)
                    if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                        response_content = msg.content
                        logger.debug(f"Captured response_content (length={len(response_content)})")

    
    # If no response content captured during streaming, get final state
    if not response_content:
        logger.debug("No response content from stream, checking final state...")
        try:
            final_state = await agent.aget_state(config)
            if final_state and hasattr(final_state, 'values') and 'messages' in final_state.values:
                final_messages = final_state.values['messages']
                # Get last AIMessage
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage) and hasattr(msg, 'content') and msg.content:
                        response_content = msg.content
                        logger.debug(f"Got response from final state (length={len(response_content)})")
                        break
        except Exception as e:
            logger.debug(f"Failed to get final state: {e}")
    
    # Determine data source from tools used
    data_source = None
    if any("suzieq" in t for t in tools_used):
        data_source = "SuzieQ 历史数据"
    elif any("netconf" in t or "nornir" in t for t in tools_used):
        data_source = "设备实时查询"
    elif any("cli" in t for t in tools_used):
        data_source = "CLI 命令执行"
    
    return {
        "content": response_content,
        "tools_used": list(set(tools_used)),  # Remove duplicates
        "data_source": data_source,
        "timings": tool_timings,
    }


async def _run_interactive_chat(thread_id: str | None = None, agent_mode: str = "react") -> None:
    """Run interactive chat loop.
    
    Args:
        thread_id: Optional thread ID for conversation context
        agent_mode: Agent architecture ('react' or 'legacy')
    """
    ui = ChatUI(console)
    
    try:
        # Import appropriate agent based on mode
        if agent_mode == "react":
            from olav.agents.root_agent_react import create_root_agent_react
            agent, checkpointer_ctx = await create_root_agent_react()
        else:  # legacy
            from olav.agents.root_agent_legacy import create_root_agent
            agent, checkpointer_ctx = await create_root_agent()
        
        logger.debug(f"Root agent ({agent_mode}) initialized successfully")
        
        # Generate thread ID if not provided
        if not thread_id:
            import time
            thread_id = f"cli-interactive-{int(time.time())}"
        
        config = {"configurable": {"thread_id": thread_id}}
        console.print(f"[dim]Session ID: {thread_id}[/dim]\n")
        
        try:
            while True:
                try:
                    # Get user input
                    user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()
                    
                    if not user_input:
                        continue
                        
                    # Handle special commands
                    if user_input.lower() in ["exit", "quit", "q"]:
                        console.print("[green]👋 再见![/green]")
                        break
                    elif user_input.lower() == "help":
                        _show_help()
                        continue
                    elif user_input.lower() == "clear":
                        console.clear()
                        continue
                    elif user_input.lower() == "status":
                        _show_status()
                        continue
                    
                    # Process query
                    console.print()
                    result = await _stream_agent_response(
                        agent=agent,
                        query=user_input,
                        config=config,
                        ui=ui,
                    )
                    
                    # Display response
                    if result["content"]:
                        ui.show_agent_response(
                            result["content"],
                            metadata={
                                "tools_used": result.get("tools_used", []),
                                "data_source": result.get("data_source"),
                                "timings": result.get("timings", []),
                            }
                        )
                    else:
                        ui.show_warning("未收到响应")
                        
                except KeyboardInterrupt:
                    console.print("\n[yellow]使用 'exit' 退出会话[/yellow]\n")
                    continue
                except EOFError:
                    console.print("\n[green]👋 再见![/green]")
                    break
        finally:
            # Cleanup checkpointer
            await checkpointer_ctx.__aexit__(None, None, None)
                
    except Exception as e:
        logger.error(f"Failed to initialize chat session: {e}", exc_info=True)
        ui.show_error(str(e))
        raise typer.Exit(1)


def _show_help() -> None:
    """Display help message."""
    help_text = """
[bold]Available Commands:[/bold]

• [cyan]help[/cyan]     - Show this help message
• [cyan]clear[/cyan]    - Clear the screen
• [cyan]status[/cyan]   - Show current configuration
• [cyan]exit[/cyan]     - Exit the chat session
• [cyan]quit[/cyan]     - Exit the chat session

[bold]Example Queries:[/bold]

• "查询设备 R1 的接口状态"
• "检查网络中是否有 BGP 问题"
• "显示设备 R2 的配置"
• "分析全网接口错误"
"""
    console.print(Panel(help_text, title="[bold]OLAV Help[/bold]", border_style="blue"))


def _show_status() -> None:
    """Display current configuration status."""
    status_text = f"""
[bold]Current Configuration:[/bold]

• LLM Provider: [cyan]{settings.llm_provider}[/cyan]
• Model: [cyan]{settings.llm_model_name}[/cyan]
• HITL: [cyan]{'Enabled' if AgentConfig.ENABLE_HITL else 'Disabled'}[/cyan]
• NetBox: [cyan]{settings.netbox_url}[/cyan]
• Max Iterations: [cyan]{AgentConfig.MAX_ITERATIONS}[/cyan]
"""
    console.print(Panel(status_text, title="[bold]Status[/bold]", border_style="blue"))


@app.command()
def suzieq(
    table: str = typer.Argument(..., help="SuzieQ table name (e.g., bgp, interfaces)"),
    method: str = typer.Option("get", "--method", "-m", help="Query method: get|summarize"),
    filter: list[str] = typer.Option([], "--filter", "-f", help="Filter in key=value form; repeatable"),
) -> None:
    """Direct one-shot SuzieQ parquet query (non-interactive) with timing output.

    Examples:
        olav suzieq bgp --method get
        olav suzieq bgp --method summarize
        olav suzieq interfaces -f hostname=r1 -f state=up
    """
    # Build filters dict
    filters_dict: dict[str, Any] = {}
    for item in filter:
        if "=" in item:
            k, v = item.split("=", 1)
            filters_dict[k.strip()] = v.strip()
    # Invoke tool
    try:
        result = asyncio.run(suzieq_query.ainvoke({"table": table, "method": method, **filters_dict}))
    except Exception as e:  # pragma: no cover - defensive
        console.print(f"[red]Query failed: {e}[/red]")
        raise typer.Exit(1)

    # Pretty print JSON with timing
    elapsed = result.get("__meta__", {}).get("elapsed_sec")
    console.print(f"[bold green]SuzieQ Query Result[/bold green] (table={table} method={method})")
    if elapsed is not None:
        console.print(f"[dim]Elapsed: {elapsed}s[/dim]")
    console.print_json(data=result)



@app.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """Start OLAV web API server.

    Args:
        host: Host to bind to
        port: Port to listen on
    """
    console.print(f"[bold blue]Starting OLAV API server on {host}:{port}[/bold blue]")

    # TODO: Implement FastAPI server
    console.print("[yellow]API server not yet implemented[/yellow]")
    console.print("Next steps:")
    console.print("1. Create FastAPI app with LangServe")
    console.print("2. Expose agent endpoints")
    console.print("3. Add WebSocket support for streaming")

    # Temporary keep-alive loop so container does not exit
    try:
        while True:
            time.sleep(300)
    except KeyboardInterrupt:
        console.print("[red]Shutting down placeholder server loop[/red]")


@app.command()
def version() -> None:
    """Display OLAV version information."""
    console.print(f"OLAV v{__version__}")
    console.print(f"Python Package Manager: uv")
    console.print(f"LLM Provider: {settings.llm_provider}")


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
