"""Root agent orchestrator using DeepAgents framework."""

import os
import sys

# Windows ProactorEventLoop fix for psycopg async
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from deepagents import create_deep_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.core.settings import settings
from config.settings import AgentConfig
from olav.agents.netconf_agent import create_netconf_subagent
from olav.agents.cli_agent import create_cli_subagent
from olav.agents.suzieq_agent import create_suzieq_subagent
from olav.agents.rag_agent import create_rag_subagent
from olav.agents.netbox_agent import create_netbox_subagent


async def create_root_agent():
    """Create root agent with SubAgent orchestration.

    Returns:
        Tuple of (agent, checkpointer_manager) - caller must manage checkpointer lifecycle

    Architecture (三级 CLI 降级策略):
        Root Agent (orchestrator)
        ├── SuzieQ Agent (read-only network analysis)
        ├── RAG Agent (schema search)
        ├── NetBox Agent (SSOT device inventory management)
        ├── NETCONF Agent (优先使用 - 生产标准)
        ├── CLI Agent (降级方案 - Schema-Aware NTC Templates + 传统 CLI)
        └── Learner Agent (episodic memory updates)
        
    三级降级工作流程:
        1. 优先: NETCONF Agent (YANG Schema + 原子回滚)
        2. 降级: CLI Agent → discover_commands (NTC Templates Schema)
        3. 兜底: CLI Agent → 传统 CLI (未验证命令，需警告用户)
    """
    # Get shared PostgreSQL checkpointer (async mode)
    checkpointer_manager = AsyncPostgresSaver.from_conn_string(settings.postgres_uri)
    checkpointer = await checkpointer_manager.__aenter__()
    
    # Setup tables if needed
    await checkpointer.setup()

    # Get LLM
    model = LLMFactory.get_chat_model()

    # Load root agent prompt with 降级策略
    root_prompt_base = prompt_manager.load_agent_prompt(
        "root_agent",
        user_name=os.getenv("USER", "operator"),
        network_context="Production network (R1, R2, R3)",  # TODO: Get from NetBox
        max_iterations=AgentConfig.MAX_ITERATIONS,
    )
    
    # 添加三级降级策略到 Prompt
    system_prompt = root_prompt_base + """

## 设备操作策略（三级降级链）

当用户请求操作设备时，遵循以下策略:

1. **优先尝试 NETCONF** (生产环境标准)
   - 调用 netconf-executor SubAgent
   - 如果收到 "NETCONF connection failed" → 执行步骤 2

2. **降级到 NTC CLI** (Schema-Aware 已验证命令)
   - 调用 cli-executor SubAgent
   - cli-executor 会先使用 discover_commands 查询已验证命令
   - 保证平台语法正确 + TextFSM 解析可用
   - ⚠️ 提醒用户: CLI 模式无原子回滚能力

3. **兜底传统 CLI** (未验证命令)
   - 仅当 discover_commands 返回 fallback_needed=True
   - cli-executor 使用推断命令（风险：语法可能错误）
   - ⚠️ 警告用户: 未找到验证模板，使用未验证命令

示例对话:
用户: "检查 R1 的接口状态"
你的思考:
1. 调用 netconf-executor(device="R1", operation="get-config", xpath="/interfaces")
2. [如果失败] 调用 cli-executor → cli-executor 内部自动:
   - 先 discover_commands(platform="cisco_ios", intent="查看接口状态")
   - 再 cli_tool(device="R1", command="show ip interface brief")
"""

    # Create SubAgents
    suzieq_subagent = create_suzieq_subagent()
    rag_subagent = create_rag_subagent()
    netbox_subagent = create_netbox_subagent()
    netconf_subagent = create_netconf_subagent()
    cli_subagent = create_cli_subagent()

    # Create root agent with DeepAgents
    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        subagents=[
            suzieq_subagent,
            rag_subagent,
            netbox_subagent,   # 🔑 SSOT 设备管理
            netconf_subagent,  # 🔑 优先尝试
            cli_subagent,      # 🔑 降级备份
        ],
        # Built-in middleware: TodoList, SubAgent, Summarization, HITL
    )

    return agent, checkpointer_manager  # Return both agent and manager for lifecycle management
