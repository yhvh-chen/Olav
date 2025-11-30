"""OLAV CLI - Enterprise Network Operations ChatOps Platform."""

import asyncio
import json
import logging
import sys
import time
from typing import Any

import typer
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console
from rich.panel import Panel

# Windows psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
    )

from config.settings import AgentConfig

from olav import __version__
from olav.core.logging_config import setup_logging
from olav.core.settings import settings
from olav.sync.rules.loader import get_hitl_required_tools

# Agent imports moved to runtime (dynamic import based on --agent-mode)
from olav.tools.suzieq_parquet_tool import suzieq_query  # Direct tool access for one-shot timing
from olav.ui import ChatUI

logger = logging.getLogger("olav.main")
console = Console()

app = typer.Typer(
    name="olav",
    help="OLAV - Omni-Layer Autonomous Verifier: Enterprise Network Operations ChatOps Platform",
    add_completion=False,
)


@app.command()
def chat(
    query: str | None = typer.Argument(None, help="Single query to execute (non-interactive mode)"),
    expert: bool = typer.Option(
        False, "--expert", "-e", help="Enable Expert Mode (Deep Dive Workflow)"
    ),
    yolo: bool = typer.Option(
        False, "--yolo", "-Y", help="YOLO mode: skip all HITL approvals (auto-approve everything)"
    ),
    lang: str = typer.Option(
        "zh", "--lang", "-l", help="Output language: zh (Chinese), en (English), ja (Japanese)"
    ),
    local: bool = typer.Option(
        False, "--local", "-L", help="Use local execution (default: remote API)"
    ),
    server: str | None = typer.Option(
        None, "--server", "-s", help="API server URL (default: http://localhost:8000)"
    ),
    thread_id: str | None = typer.Option(
        None, help="Conversation thread ID (for resuming sessions)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed logs and timestamps"
    ),
) -> None:
    """Start interactive chat session with OLAV agent.

    Architecture: Workflows Orchestrator (Modular multi-workflow system)

    Execution Modes:
        - Remote (default): Connect to LangServe API server
          → CLI Client (Rich UI) → HTTP/WebSocket → API Server → Orchestrator

        - Local (-L/--local): Direct in-process execution (legacy)
          → CLI Client → Direct Orchestrator (same process)

    Workflow Modes:
        - Normal Mode (default): 3 workflows for standard operations
          • QueryDiagnosticWorkflow: Macro (SuzieQ) → Micro (NETCONF) funnel analysis
          • DeviceExecutionWorkflow: Config changes with HITL approval
          • NetBoxManagementWorkflow: Device inventory management

        - Expert Mode (-e/--expert): Enables DeepDiveWorkflow for complex tasks
          • Automatic task decomposition (Todo List generation)
          • Recursive diagnostics (max 3 levels)
          • Batch audits (30+ devices parallel execution)
          • Progress tracking with Checkpointer (resume on interruption)

    Examples:
        # Remote mode (default) - Interactive
        uv run olav.py

        # Remote mode - Single query
        uv run olav.py "查询设备 R1 的接口状态"

        # Remote mode - Custom server
        uv run olav.py --server http://prod-olav.company.com:8000

        # Local mode - Direct execution (no API server)
        uv run olav.py -L "查询 R1"

        # Expert mode - Complex diagnostics (remote)
        uv run olav.py -e "审计所有边界路由器的 BGP 安全配置"

        # Expert mode - Local execution
        uv run olav.py -L -e "为什么数据中心 A 无法访问数据中心 B？"

        # Verbose mode (show detailed logs)
        uv run olav.py "查询 R1" --verbose

        # Resume previous conversation
        uv run olav.py --thread-id "session-123"

    Note: ReAct, Legacy, Structured, and Simple agent modes have been deprecated (2025-11-23).
          See archive/deprecated_agents/README.md for migration details.
    """
    # Setup logging first
    setup_logging(verbose)

    # Auto-fallback logic: if no explicit server and not local, try remote first then fallback
    # If user explicitly set --server, don't auto-fallback
    auto_fallback_to_local = (server is None) and (not local)

    # Determine execution mode
    exec_mode = "local" if local else "remote"
    mode_name = "Expert Mode (Deep Dive)" if expert else "Normal Mode"

    # YOLO mode: set global flag to skip HITL
    if yolo:
        AgentConfig.YOLO_MODE = True
        console.print(
            "[bold red]⚠️  YOLO MODE ENABLED - All approvals will be auto-accepted![/bold red]"
        )

    # Language setting: validate and set
    valid_langs = ("zh", "en", "ja")
    if lang not in valid_langs:
        console.print(f"[yellow]⚠️  Invalid language '{lang}', using default 'zh'[/yellow]")
        lang = "zh"
    AgentConfig.LANGUAGE = lang  # type: ignore[assignment]
    lang_names = {"zh": "中文", "en": "English", "ja": "日本語"}

    console.print(f"[bold green]OLAV v{__version__}[/bold green] - Network Operations ChatOps")
    console.print(f"LLM: {settings.llm_provider} ({settings.llm_model_name})")
    console.print("Architecture: Workflows Orchestrator")
    console.print(f"Execution: {exec_mode.capitalize()} Mode")
    console.print(f"Workflow: {mode_name}")
    console.print(f"Language: {lang_names.get(lang, lang)}")
    hitl_status = (
        "[red]YOLO (Auto-approve)[/red]"
        if yolo
        else ("Enabled" if AgentConfig.ENABLE_HITL else "Disabled")
    )
    console.print(f"HITL: {hitl_status}")

    # Windows: Use SelectorEventLoop for psycopg async compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if query:
        # Single query mode (non-interactive)
        asyncio.run(
            _run_single_query_new(query, expert, local, server, thread_id, auto_fallback_to_local)
        )
    else:
        # Interactive chat mode
        console.print("\nType 'exit' or 'quit' to end session")
        console.print("Type 'help' for available commands\n")
        asyncio.run(
            _run_interactive_chat_new(expert, local, server, thread_id, auto_fallback_to_local)
        )


async def _run_single_query_new(
    query: str,
    expert: bool = False,
    local: bool = False,
    server: str | None = None,
    thread_id: str | None = None,
    auto_fallback: bool = False,
) -> None:
    """Execute single query using new client architecture.

    Args:
        query: User query to execute
        expert: Enable Expert Mode (Deep Dive Workflow)
        local: Use local execution mode
        server: API server URL (for remote mode)
        thread_id: Optional thread ID for conversation context
        auto_fallback: Auto-fallback to local mode if remote fails
    """
    from olav.cli.client import create_client

    # Create client with auto-fallback support
    mode = "local" if local else "remote"
    client = await create_client(
        mode=mode, server_url=server, expert_mode=expert, auto_fallback=auto_fallback
    )

    # Generate thread ID if not provided
    if not thread_id:
        import time

        thread_id = f"cli-single-{int(time.time())}"

    # Show user query
    console.print()
    console.print(f"[bold green]User[/bold green]: {query}")

    # Execute query
    result = await client.execute(query, thread_id, stream=True)

    # Display result
    client.display_result(result)


async def _run_interactive_chat_new(
    expert: bool = False,
    local: bool = False,
    server: str | None = None,
    thread_id: str | None = None,
    auto_fallback: bool = False,
) -> None:
    """Run interactive chat session using new client architecture.

    Args:
        expert: Enable Expert Mode (Deep Dive Workflow)
        local: Use local execution mode
        server: API server URL (for remote mode)
        thread_id: Optional thread ID for conversation context
        auto_fallback: Auto-fallback to local mode if remote fails
    """
    from olav.cli.client import create_client

    # Create client with auto-fallback support
    mode = "local" if local else "remote"
    client = await create_client(
        mode=mode, server_url=server, expert_mode=expert, auto_fallback=auto_fallback
    )

    # Generate thread ID if not provided
    if not thread_id:
        import time

        thread_id = f"cli-interactive-{int(time.time())}"

    console.print(f"\n[dim]Thread ID: {thread_id}[/dim]\n")

    # Track HITL state
    pending_hitl: dict | None = None  # Stores interrupted workflow info

    # Interactive loop
    while True:
        try:
            # Get user input
            user_input = console.input("[bold green]You[/bold green]: ").strip()

            if not user_input:
                continue

            # Handle special commands
            if user_input.lower() in ("exit", "quit", "q"):
                console.print("\n[yellow]Goodbye! 👋[/yellow]")
                break

            if user_input.lower() == "help":
                console.print("\n[bold]Available commands:[/bold]")
                console.print("  - Type your question or command")
                console.print("  - 'exit' or 'quit' - End session")
                console.print("  - 'help' - Show this help message")
                if pending_hitl:
                    console.print("\n[bold yellow]HITL Commands (workflow paused):[/bold yellow]")
                    console.print("  - 'Y' or 'approve' - Continue with feasible tasks")
                    console.print("  - 'N' or 'abort' - Cancel workflow")
                    console.print("  - Other text - Modify execution plan")
                console.print()
                continue

            # Check if we're in HITL approval mode
            if pending_hitl:
                # User is responding to HITL prompt
                console.print(f"\n[dim]Processing HITL response: {user_input}[/dim]")

                resume_result = await client.resume(
                    thread_id=thread_id,
                    user_input=user_input,
                    workflow_type=pending_hitl["workflow_type"],
                )

                if not resume_result.success:
                    console.print(f"\n[red]❌ {resume_result.error}[/red]")
                    pending_hitl = None
                    continue

                # Check if still interrupted (modified plan needs re-approval)
                if resume_result.interrupted:
                    console.print("\n[yellow]⏸️ 计划已修改，需要重新审批[/yellow]")
                    pending_hitl = {
                        "workflow_type": resume_result.workflow_type,
                        "execution_plan": resume_result.execution_plan,
                        "todos": resume_result.todos,
                    }
                    # Display updated plan
                    _display_hitl_prompt(console, resume_result)
                else:
                    # Workflow completed
                    pending_hitl = None
                    if resume_result.messages:
                        last_msg = resume_result.messages[-1]
                        if last_msg.get("content"):
                            from rich.markdown import Markdown

                            console.print(Markdown(last_msg["content"]))
                continue

            # Normal query execution
            result = await client.execute(user_input, thread_id, stream=True)

            # Check if workflow was interrupted for HITL
            if result.interrupted:
                console.print("\n[yellow]⏸️ 工作流已暂停，等待用户审批[/yellow]")
                pending_hitl = {
                    "workflow_type": result.workflow_type,
                    "execution_plan": result.execution_plan,
                    "todos": result.todos,
                }
                # Display HITL prompt
                _display_hitl_prompt(console, result)
                continue

            # Display result (if not already shown via streaming)
            if not result.success:
                client.display_result(result)

        except KeyboardInterrupt:
            console.print("\n\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
            continue
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            logger.exception("Interactive chat error")


def _display_hitl_prompt(console, result) -> None:
    """Display HITL approval prompt with execution plan details."""
    execution_plan = result.execution_plan or {}
    todos = result.todos or []

    # Build task map
    task_map = {}
    for t in todos:
        if isinstance(t, dict):
            task_map[t.get("id")] = t.get("task", "(描述缺失)")

    feasible = execution_plan.get("feasible_tasks", [])
    uncertain = execution_plan.get("uncertain_tasks", [])
    infeasible = execution_plan.get("infeasible_tasks", [])
    recommendations = execution_plan.get("recommendations", {})

    console.print("\n" + "=" * 60)
    console.print("[bold]🗂️ 执行计划[/bold]")
    console.print("=" * 60)

    summary = execution_plan.get("summary") or execution_plan.get("plan_summary")
    if summary:
        console.print(summary)
        console.print("-" * 60)

    if feasible:
        console.print(f"\n[green]✅ 可执行任务 ({len(feasible)} 个):[/green]")
        for task_id in feasible:
            desc = task_map.get(task_id, "(描述缺失)")
            console.print(f"  - 任务 {task_id}: {desc}")
            if task_id in recommendations:
                console.print(f"    建议: {recommendations[task_id]}")

    if uncertain:
        console.print(f"\n[yellow]⚠️ 需进一步确认的任务 ({len(uncertain)} 个):[/yellow]")
        for task_id in uncertain:
            desc = task_map.get(task_id, "(描述缺失)")
            console.print(f"  - 任务 {task_id}: {desc}")
            if task_id in recommendations:
                console.print(f"    建议: {recommendations[task_id]}")

    if infeasible:
        console.print(f"\n[red]❌ 无法执行任务 ({len(infeasible)} 个):[/red]")
        for task_id in infeasible:
            desc = task_map.get(task_id, "(描述缺失)")
            console.print(f"  - 任务 {task_id}: {desc}")
            if task_id in recommendations:
                console.print(f"    建议: {recommendations[task_id]}")

    console.print("\n" + "=" * 60)
    console.print("[bold]请选择操作:[/bold]")
    console.print("  [green]Y / approve[/green] - 批准执行可行任务")
    console.print("  [red]N / abort[/red] - 中止执行")
    console.print("  [cyan]其他文本[/cyan] - 输入修改请求")
    console.print("=" * 60)


async def _run_single_query(query: str, expert: bool = False, thread_id: str | None = None) -> None:
    """Execute single query and exit.

    Args:
        query: User query to execute
        expert: Enable Expert Mode (Deep Dive Workflow)
        thread_id: Optional thread ID for conversation context
    """
    ui = ChatUI(console)

    try:
        # Import Workflows Orchestrator
        from olav.agents.root_agent_orchestrator import create_workflow_orchestrator

        orchestrator, agent, checkpointer_ctx = await create_workflow_orchestrator(
            expert_mode=expert
        )

        logger.debug(f"Workflows Orchestrator initialized successfully (expert_mode={expert})")

        # Generate thread ID if not provided
        if not thread_id:
            import time

            thread_id = f"cli-single-{int(time.time())}"

        config = {"configurable": {"thread_id": thread_id}}

        # Show user query
        console.print()
        ui.show_user_message(query)

        # First, route via orchestrator directly to obtain structured plan (needed for task descriptions)
        route_result = await orchestrator.route(query, thread_id)

        # If interrupted, use route_result directly (contains execution_plan & todos)
        if route_result.get("interrupted"):
            console.print("\n[bold yellow]⏸️  执行已暂停，等待用户审批[/bold yellow]")
            execution_plan = route_result.get("execution_plan", {})
            todos = route_result.get("todos", [])
            # Build a mapping from id -> task text for display
            task_map = {t.get("id"): t.get("task") for t in todos if isinstance(t, dict)}

            # Display execution plan
            console.print("\n" + "=" * 60)
            console.print("[bold cyan]📋 执行计划（Schema 调研结果）[/bold cyan]")
            console.print("=" * 60)

            feasible = execution_plan.get("feasible_tasks", [])
            uncertain = execution_plan.get("uncertain_tasks", [])
            infeasible = execution_plan.get("infeasible_tasks", [])

            if feasible:
                console.print(f"\n[green]✅ 可执行任务 ({len(feasible)} 个):[/green]")
                for task_id in feasible:
                    desc = task_map.get(task_id, "(描述缺失)")
                    console.print(f"  - 任务 {task_id}: {desc}")

            if uncertain:
                console.print(f"\n[yellow]⚠️  不确定任务 ({len(uncertain)} 个):[/yellow]")
                for task_id in uncertain:
                    desc = task_map.get(task_id, "(描述缺失)")
                    console.print(f"  - 任务 {task_id}: {desc}")
                    recs = execution_plan.get("recommendations", {})
                    if task_id in recs:
                        console.print(f"    建议: {recs[task_id]}")

            if infeasible:
                console.print(f"\n[red]❌ 无法执行任务 ({len(infeasible)} 个):[/red]")
                for task_id in infeasible:
                    desc = task_map.get(task_id, "(描述缺失)")
                    console.print(f"  - 任务 {task_id}: {desc}")

            console.print("\n" + "=" * 60)
            console.print("[bold]请选择操作:[/bold]")
            console.print("  [green]Y[/green] - 批准执行可行任务")
            console.print("  [red]N[/red] - 中止执行")
            console.print(
                "  [cyan]其他[/cyan] - 输入修改请求（例如：'跳过任务2，使用bgp表执行任务5'）"
            )
            console.print("=" * 60)

            # Enter approval loop
            while True:
                user_input = input("\n您的决定: ").strip()

                if not user_input:
                    console.print("[yellow]请输入有效选择 (Y/N/修改请求)[/yellow]")
                    continue

                # Resume execution with user input
                console.print(f"\n[dim]处理用户输入: {user_input}[/dim]")

                # Convert workflow_type string to enum
                from olav.workflows.base import WorkflowType

                workflow_enum = WorkflowType[route_result["workflow_type"].upper()]

                resume_result = await orchestrator.resume(
                    thread_id=thread_id, user_input=user_input, workflow_type=workflow_enum
                )

                # Check if resume resulted in another interrupt (modified plan needs re-approval)
                if resume_result.get("interrupted"):
                    console.print("\n[yellow]⏸️  计划已修改，需要重新审批[/yellow]")
                    execution_plan = resume_result.get("execution_plan", {})
                    todos = resume_result.get("todos", todos)
                    task_map = {t.get("id"): t.get("task") for t in todos if isinstance(t, dict)}
                    # Re-display updated execution plan for re-approval
                    feasible = execution_plan.get("feasible_tasks", [])
                    uncertain = execution_plan.get("uncertain_tasks", [])
                    infeasible = execution_plan.get("infeasible_tasks", [])

                    console.print("\n" + "=" * 60)
                    console.print("[bold]🗂️ 更新后的执行计划[/bold]")
                    console.print("=" * 60)
                    summary = execution_plan.get("summary") or execution_plan.get("plan_summary")
                    if summary:
                        console.print(summary)
                        console.print("-" * 60)

                    if feasible:
                        console.print(f"[green]✅ 可执行任务 ({len(feasible)} 个):[/green]")
                        for task_id in feasible:
                            desc = task_map.get(task_id, "(描述缺失)")
                            console.print(f"  - 任务 {task_id}: {desc}")
                            recs = execution_plan.get("recommendations", {})
                            if task_id in recs:
                                console.print(f"    建议: {recs[task_id]}")

                    if uncertain:
                        console.print(
                            f"\n[yellow]⚠️  需进一步确认的任务 ({len(uncertain)} 个):[/yellow]"
                        )
                        for task_id in uncertain:
                            desc = task_map.get(task_id, "(描述缺失)")
                            console.print(f"  - 任务 {task_id}: {desc}")
                            recs = execution_plan.get("recommendations", {})
                            if task_id in recs:
                                console.print(f"    建议: {recs[task_id]}")

                    if infeasible:
                        console.print(f"\n[red]❌ 无法执行任务 ({len(infeasible)} 个):[/red]")
                        for task_id in infeasible:
                            desc = task_map.get(task_id, "(描述缺失)")
                            console.print(f"  - 任务 {task_id}: {desc}")

                    console.print("\n" + "=" * 60)
                    console.print("[bold]请选择操作:[/bold]")
                    console.print("  [green]Y[/green] - 批准执行可行任务")
                    console.print("  [red]N[/red] - 中止执行")
                    console.print("  [cyan]其他[/cyan] - 输入进一步修改请求")
                    console.print("=" * 60)
                    continue

                # Execution completed or aborted
                if resume_result.get("content"):
                    ui.show_agent_response(
                        resume_result["content"],
                        metadata={
                            "tools_used": resume_result.get("tools_used", []),
                            "data_source": resume_result.get("data_source"),
                        },
                    )
                break

        else:
            # Fallback to streaming standard response if no interrupt
            stream_result = await _stream_agent_response(
                agent=agent,
                query=query,
                config=config,
                ui=ui,
            )
            if stream_result.get("content"):
                ui.show_agent_response(
                    stream_result["content"],
                    metadata={
                        "tools_used": stream_result.get("tools_used", []),
                        "data_source": stream_result.get("data_source"),
                        "timings": stream_result.get("timings", []),
                    },
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
    # Tools requiring HITL approval - loaded from config/rules/hitl_config.yaml
    hitl_required_tools = get_hitl_required_tools()

    with ui.create_thinking_context() as live:
        seen_tool_ids = set()  # Track processed tool calls

        async for chunk in agent.astream(
            {"messages": [HumanMessage(content=query)]},
            config=config,
            stream_mode="values",  # Get full state each update
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
                                    if any(
                                        kw in description
                                        for kw in [
                                            "schema",
                                            "字段",
                                            "表结构",
                                            "available",
                                            "fields",
                                        ]
                                    ):
                                        display_tool_name = "suzieq_schema_search"
                                    else:
                                        display_tool_name = "suzieq_query"
                                elif subagent_type == "netconf-executor":
                                    display_tool_name = "netconf_tool"
                                elif subagent_type == "rag-helper":
                                    display_tool_name = "rag_search"
                                else:
                                    # Keep subagent_type as fallback
                                    display_tool_name = (
                                        subagent_type if subagent_type else tool_name
                                    )

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
                            elif tool_name == "netbox_api_call" and any(
                                tag in op_lower
                                for tag in [
                                    '"method":"post"',
                                    '"method":"put"',
                                    '"method":"patch"',
                                    '"method":"delete"',
                                ]
                            ):
                                requires_gate = True
                                risk_note = "netbox-write"

                            if hitl_enabled and tool_name in hitl_required_tools and requires_gate:
                                console.print("\n[bold yellow]🔔 HITL 审批请求[/bold yellow]")
                                console.print(f"工具: [cyan]{tool_name}[/cyan]")
                                console.print(f"风险类型: [magenta]{risk_note}[/magenta]")
                                console.print(f"参数: [dim]{tool_args}[/dim]")
                                decision = input("批准此操作? [Y/n/i(详情)]: ").strip().lower()
                                if decision == "i":
                                    console.print("\n[bold]详细参数 (JSON):[/bold]")
                                    try:
                                        console.print(
                                            json.dumps(tool_args, indent=2, ensure_ascii=False)
                                        )
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
                                console.print("[green]✅ 已批准，继续执行...[/green]")

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
                        node, tool_name = current_nodes[
                            tool_id
                        ]  # tool_name is already the display name
                        ui.mark_tool_complete(node, tool_name, success=True)

                        # Calculate elapsed time
                        if tool_id in tool_start_times:
                            elapsed = time.perf_counter() - tool_start_times[tool_id]
                            tool_timings.append(
                                {
                                    "tool": tool_name,
                                    "elapsed_sec": elapsed,
                                }
                            )

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
            if final_state and hasattr(final_state, "values") and "messages" in final_state.values:
                final_messages = final_state.values["messages"]
                # Get last AIMessage
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage) and hasattr(msg, "content") and msg.content:
                        response_content = msg.content
                        logger.debug(
                            f"Got response from final state (length={len(response_content)})"
                        )
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

    # Check for HITL interrupt in final state
    interrupted = chunk.get("interrupted", False) if isinstance(chunk, dict) else False
    execution_plan = chunk.get("execution_plan") if isinstance(chunk, dict) else None
    workflow_type = chunk.get("workflow_type") if isinstance(chunk, dict) else None

    return {
        "content": response_content,
        "tools_used": list(set(tools_used)),  # Remove duplicates
        "data_source": data_source,
        "timings": tool_timings,
        "interrupted": interrupted,
        "execution_plan": execution_plan,
        "workflow_type": workflow_type,
    }


async def _run_interactive_chat(expert: bool = False, thread_id: str | None = None) -> None:
    """Run interactive chat loop.

    Args:
        expert: Enable Expert Mode (Deep Dive Workflow)
        thread_id: Optional thread ID for conversation context
    """
    ui = ChatUI(console)

    try:
        # Import Workflows Orchestrator
        from olav.agents.root_agent_orchestrator import create_workflow_orchestrator

        _orchestrator, agent, checkpointer_ctx = await create_workflow_orchestrator(
            expert_mode=expert
        )

        logger.debug(f"Workflows Orchestrator initialized successfully (expert_mode={expert})")

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
                    if user_input.lower() == "help":
                        _show_help()
                        continue
                    if user_input.lower() == "clear":
                        console.clear()
                        continue
                    if user_input.lower() == "status":
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
                            },
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
• HITL: [cyan]{"Enabled" if AgentConfig.ENABLE_HITL else "Disabled"}[/cyan]
• NetBox: [cyan]{settings.netbox_url}[/cyan]
• Max Iterations: [cyan]{AgentConfig.MAX_ITERATIONS}[/cyan]
"""
    console.print(Panel(status_text, title="[bold]Status[/bold]", border_style="blue"))


@app.command()
def suzieq(
    table: str = typer.Argument(..., help="SuzieQ table name (e.g., bgp, interfaces)"),
    method: str = typer.Option("get", "--method", "-m", help="Query method: get|summarize"),
    filter: list[str] = typer.Option(
        [], "--filter", "-f", help="Filter in key=value form; repeatable"
    ),
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
        result = asyncio.run(
            suzieq_query.ainvoke({"table": table, "method": method, **filters_dict})
        )
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
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
) -> None:
    """Start OLAV web API server.

    Launches the FastAPI server with LangServe endpoints for remote orchestrator access.

    Endpoints:
        - POST /orchestrator/invoke - Execute orchestrator synchronously
        - POST /orchestrator/stream - Stream orchestrator response
        - GET /health - Health check
        - GET /docs - OpenAPI documentation (Swagger UI)

    Examples:
        # Start server on default port
        uv run python -m olav.main serve

        # Custom port
        uv run python -m olav.main serve --port 8080

        # Development mode with auto-reload
        uv run python -m olav.main serve --reload

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to listen on (default: 8000)
        reload: Enable auto-reload for development
    """
    import uvicorn

    console.print(f"[bold blue]Starting OLAV API server on {host}:{port}[/bold blue]")
    console.print("[dim]Endpoints:[/dim]")
    console.print("  POST /orchestrator/invoke  - Execute query")
    console.print("  POST /orchestrator/stream  - Stream response")
    console.print("  GET  /health               - Health check")
    console.print("  GET  /docs                 - OpenAPI docs")
    console.print()

    try:
        uvicorn.run(
            "olav.server.app:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
        )
    except KeyboardInterrupt:
        console.print("[yellow]Server shutting down...[/yellow]")


@app.command()
def login(
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        help="API server URL (default: OLAV_SERVER_URL or http://localhost:8000)",
    ),
) -> None:
    """Login to OLAV API server and store authentication token.

    Interactive command that prompts for username and password,
    then stores JWT token in ~/.olav/credentials for future use.

    Examples:
        # Login to default server (localhost:8000)
        uv run olav.py login

        # Login to production server
        uv run olav.py login --server https://olav-prod.company.com
    """
    from olav.cli import login_interactive

    try:
        asyncio.run(login_interactive(server_url=server))
    except (ValueError, ConnectionError) as e:
        logger.error(f"Login failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def logout() -> None:
    """Logout from OLAV API server (delete stored credentials).

    Removes JWT token from ~/.olav/credentials file.
    Note: JWT tokens are stateless, so server-side logout is not needed.

    Example:
        uv run olav.py logout
    """
    from olav.cli import logout_interactive

    try:
        asyncio.run(logout_interactive())
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def whoami() -> None:
    """Show current authentication status and user information.

    Displays:
        - Username
        - Server URL
        - Token expiration time
        - Authentication status

    Example:
        uv run olav.py whoami
    """
    from olav.cli import whoami_interactive

    try:
        asyncio.run(whoami_interactive())
    except Exception as e:
        logger.error(f"Failed to check auth status: {e}")
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Display OLAV version information."""
    console.print(f"OLAV v{__version__}")
    console.print("Python Package Manager: uv")
    console.print(f"LLM Provider: {settings.llm_provider}")


@app.command()
def inspect(
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Inspection profile name (from config/inspections/)"
    ),
    config_path: str | None = typer.Option(
        None, "--config", "-c", help="Path to inspection config YAML file"
    ),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as background scheduler daemon"),
    lang: str = typer.Option(
        "zh", "--lang", "-l", help="Report language: zh (Chinese), en (English), ja (Japanese)"
    ),
    list_profiles: bool = typer.Option(False, "--list", help="List available inspection profiles"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed logs"),
) -> None:
    """Run automated network inspection (no HITL required).

    Inspections are read-only health checks that run without user approval.
    Results are saved as timestamped Markdown reports in data/inspection-reports/.

    Modes:
        - One-shot (default): Run inspection once and exit
        - Daemon (-d/--daemon): Run scheduler in background with periodic execution

    Configuration:
        Inspection profiles are defined in config/inspections/*.yaml
        Each profile specifies:
        - Target devices (list, NetBox filter, or regex)
        - Checks to run (SuzieQ queries with thresholds)
        - Severity levels (critical, warning, info)

    Examples:
        # List available profiles
        uv run olav.py inspect --list

        # Run default inspection profile
        uv run olav.py inspect

        # Run specific profile
        uv run olav.py inspect -p bgp_peer_audit

        # Run with custom config file
        uv run olav.py inspect -c my_inspection.yaml

        # Start scheduler daemon (runs on schedule from config)
        uv run olav.py inspect --daemon

        # Run in English
        uv run olav.py inspect -p daily_core_check -l en
    """
    setup_logging(verbose)

    # Validate language
    valid_langs = ("zh", "en", "ja")
    if lang not in valid_langs:
        console.print(f"[yellow]⚠️  Invalid language '{lang}', using default 'zh'[/yellow]")
        lang = "zh"
    AgentConfig.LANGUAGE = lang  # type: ignore

    # Windows async compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # List profiles mode
    if list_profiles:
        from config.settings import Paths

        profile_dir = Paths.INSPECTIONS_DIR
        console.print("\n[bold]Available Inspection Profiles:[/bold]")
        if profile_dir.exists():
            for yaml_file in sorted(profile_dir.glob("*.yaml")):
                # Try to get description from file
                try:
                    import yaml

                    with open(yaml_file, encoding="utf-8") as f:
                        cfg = yaml.safe_load(f)
                        name = cfg.get("name", yaml_file.stem)
                        desc = cfg.get("description", "")
                        console.print(f"  • [cyan]{yaml_file.stem}[/cyan]: {name}")
                        if desc:
                            console.print(f"    {desc}")
                except Exception:
                    console.print(f"  • [cyan]{yaml_file.stem}[/cyan]")
        else:
            console.print(
                "[yellow]  No profiles found. Create profiles in config/inspections/[/yellow]"
            )
        return

    # Daemon mode
    if daemon:
        from config.settings import InspectionConfig

        console.print(
            Panel.fit(
                f"[bold green]OLAV Inspection Scheduler[/bold green]\n\n"
                f"Profile: {InspectionConfig.DEFAULT_PROFILE}\n"
                f"Schedule: {InspectionConfig.SCHEDULE_CRON or f'Daily at {InspectionConfig.SCHEDULE_TIME}'}\n"
                f"Reports: {InspectionConfig.REPORTS_DIR}\n\n"
                "[dim]Press Ctrl+C to stop[/dim]",
                title="Daemon Mode",
            )
        )

        from olav.inspection.scheduler import run_scheduler

        asyncio.run(run_scheduler())
        return

    # One-shot inspection mode
    from olav.inspection.runner import run_inspection

    profile_name = profile or "daily_core_check"
    console.print(f"\n[bold]Running Inspection: {profile_name}[/bold]")
    console.print(f"Language: {lang}")
    console.print("[dim]This is a read-only check (no HITL required)[/dim]\n")

    try:
        result = asyncio.run(
            run_inspection(
                profile=profile_name if not config_path else None,
                config_path=config_path,
                language=lang,
            )
        )

        if result.get("status") == "success":
            passed = result.get("passed", 0)
            total = result.get("total_checks", 0)
            critical = result.get("critical", 0)
            duration = result.get("duration_seconds", 0)
            report_path = result.get("report_path", "")

            # Summary
            status_emoji = "🔴" if critical > 0 else ("🟡" if passed < total else "🟢")
            console.print(f"\n{status_emoji} [bold]Inspection Complete[/bold]")
            console.print(f"  ✅ Passed: {passed}/{total}")
            if critical > 0:
                console.print(f"  🔴 Critical: {critical}")
            console.print(f"  ⏱️  Duration: {duration:.1f}s")
            console.print(f"  📄 Report: [link=file://{report_path}]{report_path}[/link]")
        else:
            console.print(f"\n[red]❌ Inspection failed: {result.get('message')}[/red]")
            raise typer.Exit(code=1)

    except FileNotFoundError as e:
        console.print(f"\n[red]❌ Profile not found: {e}[/red]")
        console.print("[dim]Use --list to see available profiles[/dim]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"\n[red]❌ Inspection error: {e}[/red]")
        logger.exception("Inspection failed")
        raise typer.Exit(code=1)


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
