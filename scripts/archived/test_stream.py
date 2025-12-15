#!/usr/bin/env python
"""轻量级流式传输测试脚本.

测试 LangChain/LangGraph 的三种流式模式：
1. LLM Token 级别流式 (包括 reasoning/thinking)
2. Graph 状态流式
3. 事件流式 (astream_events)

用法:
    uv run python scripts/test_stream.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

# 加载 .env
load_dotenv(Path(__file__).parent.parent / ".env")


async def test_1_llm_token_stream():
    """测试 1: LLM Token 级别流式输出."""
    print("\n" + "=" * 60)
    print("测试 1: LLM Token 级别流式输出")
    print("=" * 60)
    
    from langchain_ollama import ChatOllama
    
    # 获取配置
    base_url = os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434")
    model = os.getenv("LLM_MODEL_NAME", "qwen3:30b")
    
    print(f"模型: {model}")
    print(f"Base URL: {base_url}")
    
    # 创建模型 - 启用 reasoning 模式
    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=0.7,
        reasoning=True,  # 启用思考模式 (qwen3, deepseek 等支持)
    )
    
    print("\n--- 流式输出 (astream) ---")
    query = "9.11 和 9.9 哪个大？用一句话回答"
    print(f"Query: {query}\n")
    
    reasoning_buffer = ""
    content_buffer = ""
    
    async for chunk in llm.astream(query):
        # 正常响应内容
        if chunk.content:
            content_buffer += chunk.content
            print(f"{chunk.content}", end="", flush=True)
        
        # reasoning_content 在 additional_kwargs 中！
        reasoning = chunk.additional_kwargs.get("reasoning_content", "")
        if reasoning:
            reasoning_buffer += reasoning
            # 实时显示思考过程
            print(f"\n💭 {reasoning}", end="", flush=True)
    
    print("\n\n--- 汇总 ---")
    print(f"思考过程 ({len(reasoning_buffer)} chars):")
    if reasoning_buffer:
        print(reasoning_buffer[:500] + "..." if len(reasoning_buffer) > 500 else reasoning_buffer)
    print(f"\n最终响应 ({len(content_buffer)} chars):")
    print(content_buffer)


async def test_2_graph_state_stream():
    """测试 2: Graph 状态流式输出."""
    print("\n" + "=" * 60)
    print("测试 2: Graph 状态流式输出 (stream_mode='values')")
    print("=" * 60)
    
    from typing import Annotated, TypedDict
    from langchain_ollama import ChatOllama
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    
    # 定义状态
    class State(TypedDict):
        messages: Annotated[list, add_messages]
        step: str
    
    # 获取 LLM
    base_url = os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434")
    model = os.getenv("LLM_MODEL_NAME", "qwen3:30b")
    llm = ChatOllama(model=model, base_url=base_url, temperature=0.7)
    
    # 定义节点
    def analyze_node(state: State) -> State:
        print("  [Node: analyze] 执行中...")
        return {"step": "analyze", "messages": []}
    
    async def llm_node(state: State) -> State:
        print("  [Node: llm] 调用 LLM...")
        response = await llm.ainvoke(state["messages"])
        return {"step": "llm", "messages": [response]}
    
    # 构建图
    graph = StateGraph(State)
    graph.add_node("analyze", analyze_node)
    graph.add_node("llm", llm_node)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "llm")
    graph.add_edge("llm", END)
    
    app = graph.compile()
    
    print("\n--- stream_mode='values' (完整状态) ---")
    initial_state = {"messages": [("user", "你好")], "step": "start"}
    
    async for chunk in app.astream(initial_state, stream_mode="values"):
        print(f"  State update: step={chunk.get('step')}, msgs={len(chunk.get('messages', []))}")
    
    print("\n--- stream_mode='updates' (增量更新) ---")
    async for chunk in app.astream(initial_state, stream_mode="updates"):
        for node_name, update in chunk.items():
            print(f"  Node '{node_name}' update: {list(update.keys())}")


async def test_3_astream_events():
    """测试 3: 事件流式输出 (astream_events) - 最细粒度."""
    print("\n" + "=" * 60)
    print("测试 3: 事件流式输出 (astream_events)")
    print("=" * 60)
    
    from typing import Annotated, TypedDict
    from langchain_ollama import ChatOllama
    from langchain_core.tools import tool
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    from langgraph.prebuilt import ToolNode
    
    # 定义简单工具
    @tool
    def get_weather(city: str) -> str:
        """获取城市天气."""
        return f"{city} 今天晴，25°C"
    
    tools = [get_weather]
    
    # 定义状态
    class State(TypedDict):
        messages: Annotated[list, add_messages]
    
    # 获取 LLM - 启用 reasoning
    base_url = os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434")
    model = os.getenv("LLM_MODEL_NAME", "qwen3:30b")
    llm = ChatOllama(
        model=model, 
        base_url=base_url, 
        temperature=0.7,
        reasoning=True,  # 启用思考模式
    ).bind_tools(tools)
    
    # 定义节点
    async def agent_node(state: State) -> State:
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}
    
    def should_continue(state: State):
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return END
    
    # 构建图
    graph = StateGraph(State)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    
    app = graph.compile()
    
    print("\n--- astream_events (事件流) ---")
    print("事件类型说明:")
    print("  on_chat_model_stream - LLM Token (包含 reasoning_content)")
    print("  on_tool_start        - 工具开始")
    print("  on_tool_end          - 工具结束")
    print()
    
    query = "9.11 和 9.9 哪个大？"
    print(f"Query: {query}\n")
    
    initial_state = {"messages": [("user", query)]}
    
    token_count = 0
    reasoning_buffer = ""
    content_buffer = ""
    
    async for event in app.astream_events(initial_state, version="v2"):
        event_type = event.get("event", "")
        
        if event_type == "on_chat_model_start":
            print(f"🚀 [LLM START]")
        
        elif event_type == "on_chat_model_stream":
            # 这是 Token 级别的流式输出
            chunk = event.get("data", {}).get("chunk")
            if chunk:
                # 正常内容
                content = getattr(chunk, "content", "")
                if content:
                    token_count += 1
                    content_buffer += content
                    print(content, end="", flush=True)
                
                # ⭐ 关键: reasoning_content 在 additional_kwargs 中
                additional = getattr(chunk, "additional_kwargs", {})
                reasoning = additional.get("reasoning_content", "")
                if reasoning:
                    reasoning_buffer += reasoning
                    print(f"\n💭 {reasoning}", end="", flush=True)
        
        elif event_type == "on_chat_model_end":
            print(f"\n✅ [LLM END] tokens={token_count}")
            token_count = 0
        
        elif event_type == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            print(f"🔧 [TOOL START] {tool_name}({tool_input})")
        
        elif event_type == "on_tool_end":
            tool_name = event.get("name", "unknown")
            tool_output = event.get("data", {}).get("output", "")
            print(f"✅ [TOOL END] {tool_name} -> {str(tool_output)[:100]}")
    
    print("\n\n--- 汇总 ---")
    print(f"思考过程 ({len(reasoning_buffer)} chars): {reasoning_buffer[:300]}...")
    print(f"最终响应 ({len(content_buffer)} chars): {content_buffer}")


async def test_4_subgraph_stream():
    """测试 4: 子图状态流式输出."""
    print("\n" + "=" * 60)
    print("测试 4: 子图 (Subgraph) 状态流式输出")
    print("=" * 60)
    
    from typing import Annotated, TypedDict
    from langchain_ollama import ChatOllama
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    
    # 定义状态
    class SubState(TypedDict):
        messages: Annotated[list, add_messages]
        sub_step: str
    
    class MainState(TypedDict):
        messages: Annotated[list, add_messages]
        main_step: str
    
    # 获取 LLM
    base_url = os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434")
    model = os.getenv("LLM_MODEL_NAME", "qwen3:30b")
    llm = ChatOllama(model=model, base_url=base_url, temperature=0.7)
    
    # 创建子图
    def sub_analyze(state: SubState) -> SubState:
        print("    [SubGraph: analyze] 分析中...")
        return {"sub_step": "sub_analyze"}
    
    async def sub_respond(state: SubState) -> SubState:
        print("    [SubGraph: respond] 生成响应...")
        response = await llm.ainvoke(state["messages"])
        return {"sub_step": "sub_respond", "messages": [response]}
    
    subgraph = StateGraph(SubState)
    subgraph.add_node("sub_analyze", sub_analyze)
    subgraph.add_node("sub_respond", sub_respond)
    subgraph.add_edge(START, "sub_analyze")
    subgraph.add_edge("sub_analyze", "sub_respond")
    subgraph.add_edge("sub_respond", END)
    sub_app = subgraph.compile()
    
    # 创建主图
    def preprocess(state: MainState) -> MainState:
        print("  [MainGraph: preprocess] 预处理...")
        return {"main_step": "preprocess"}
    
    async def call_subgraph(state: MainState) -> MainState:
        print("  [MainGraph: call_subgraph] 调用子图...")
        # 直接调用子图
        sub_result = await sub_app.ainvoke({
            "messages": state["messages"],
            "sub_step": "start"
        })
        return {
            "main_step": "subgraph_done",
            "messages": sub_result["messages"]
        }
    
    def postprocess(state: MainState) -> MainState:
        print("  [MainGraph: postprocess] 后处理...")
        return {"main_step": "done"}
    
    main_graph = StateGraph(MainState)
    main_graph.add_node("preprocess", preprocess)
    main_graph.add_node("call_subgraph", call_subgraph)
    main_graph.add_node("postprocess", postprocess)
    main_graph.add_edge(START, "preprocess")
    main_graph.add_edge("preprocess", "call_subgraph")
    main_graph.add_edge("call_subgraph", "postprocess")
    main_graph.add_edge("postprocess", END)
    
    main_app = main_graph.compile()
    
    print("\n--- 主图 + 子图流式输出 ---")
    initial_state = {"messages": [("user", "你好")], "main_step": "start"}
    
    print("\n使用 astream_events 追踪所有事件:")
    async for event in main_app.astream_events(initial_state, version="v2"):
        event_type = event.get("event", "")
        name = event.get("name", "")
        
        # 只显示关键事件
        if event_type in ["on_chain_start", "on_chain_end"]:
            if "graph" in name.lower() or "langgraph" in name.lower():
                print(f"  📊 {event_type}: {name}")
        elif event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and getattr(chunk, "content", ""):
                print(chunk.content, end="", flush=True)
    
    print("\n")


async def test_5_reasoning_extraction():
    """测试 5: 提取 qwen3/deepseek 的思考过程."""
    print("\n" + "=" * 60)
    print("测试 5: 提取模型思考过程 (reasoning_content)")
    print("=" * 60)
    
    from langchain_ollama import ChatOllama
    
    base_url = os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434")
    model = os.getenv("LLM_MODEL_NAME", "qwen3:30b")
    
    print(f"模型: {model}")
    print(f"Base URL: {base_url}")
    
    # 测试不同的 reasoning 配置
    configs = [
        {"reasoning": True, "desc": "reasoning=True"},
        {"reasoning": "detailed", "desc": "reasoning='detailed'"},
    ]
    
    for config in configs:
        print(f"\n--- 配置: {config['desc']} ---")
        
        llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0.7,
            reasoning=config["reasoning"],
        )
        
        query = "9.11 和 9.9 哪个大？"
        print(f"Query: {query}\n")
        
        thinking_content = ""
        response_content = ""
        
        async for chunk in llm.astream(query):
            # 收集正常响应
            if chunk.content:
                response_content += chunk.content
                print(f"[CONTENT] {chunk.content}", end="", flush=True)
            
            # 检查所有可能包含思考内容的属性
            if hasattr(chunk, "reasoning_content") and chunk.reasoning_content:
                thinking_content += chunk.reasoning_content
                print(f"\n[REASONING_CONTENT] {chunk.reasoning_content}", flush=True)
            
            # 检查 response_metadata
            if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                meta = chunk.response_metadata
                if "thinking" in str(meta).lower() or "reason" in str(meta).lower():
                    print(f"\n[METADATA] {meta}", flush=True)
            
            # 检查 additional_kwargs
            if chunk.additional_kwargs:
                for key, value in chunk.additional_kwargs.items():
                    if value and ("think" in key.lower() or "reason" in key.lower()):
                        print(f"\n[{key.upper()}] {value}", flush=True)
        
        print(f"\n\n总结: thinking={len(thinking_content)} chars, response={len(response_content)} chars")


async def main():
    """运行所有测试."""
    print("=" * 60)
    print("LangChain/LangGraph 流式传输测试")
    print("=" * 60)
    
    tests = [
        ("1", "LLM Token 流式", test_1_llm_token_stream),
        ("2", "Graph 状态流式", test_2_graph_state_stream),
        ("3", "事件流式 (astream_events)", test_3_astream_events),
        ("4", "子图流式", test_4_subgraph_stream),
        ("5", "思考过程提取", test_5_reasoning_extraction),
    ]
    
    print("\n选择测试:")
    for num, name, _ in tests:
        print(f"  {num}. {name}")
    print("  a. 运行全部")
    print("  q. 退出")
    
    choice = input("\n请选择 (1-5/a/q): ").strip().lower()
    
    if choice == "q":
        return
    elif choice == "a":
        for _, name, test_func in tests:
            try:
                await test_func()
            except Exception as e:
                print(f"\n❌ 测试失败: {e}")
                import traceback
                traceback.print_exc()
    else:
        for num, name, test_func in tests:
            if num == choice:
                try:
                    await test_func()
                except Exception as e:
                    print(f"\n❌ 测试失败: {e}")
                    import traceback
                    traceback.print_exc()
                break
        else:
            print("无效选择")


if __name__ == "__main__":
    asyncio.run(main())
