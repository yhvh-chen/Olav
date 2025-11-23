#!/usr/bin/env python3
"""
HITL审批流程自动化测试脚本

测试场景:
1. Y批准 - 执行可行任务
2. N中止 - 终止执行
3. 修改请求 - LLM分析并更新计划
"""

import asyncio
import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
from olav.workflows.base import WorkflowType


async def test_approval_workflow():
    """测试完整的HITL审批工作流"""
    
    print("=" * 80)
    print("HITL 审批流程测试")
    print("=" * 80)
    
    # 初始化orchestrator
    orchestrator, graph, checkpointer_ctx = await create_workflow_orchestrator(expert_mode=True)
    
    try:
        # 测试查询
        query = "审计生产环境所有路由器的MPLS配置完整性"
        thread_id = "test-hitl-approval"
        
        print(f"\n📝 用户查询: {query}")
        print(f"🔗 Thread ID: {thread_id}\n")
        
        # 1. 首次执行 - 应该触发中断
        print("=" * 80)
        print("阶段 1: 初始执行（应触发中断）")
        print("=" * 80)
        
        result = await orchestrator.route(query, thread_id)
        
        if result.get("interrupted"):
            print("\n✅ 成功触发中断")
            print(f"工作流类型: {result.get('workflow_type')}")
            print(f"下一节点: {result.get('next_node')}")
            
            execution_plan = result.get("execution_plan", {})
            print("\n📋 执行计划:")
            print(f"  可行任务: {execution_plan.get('feasible_tasks', [])}")
            print(f"  不确定任务: {execution_plan.get('uncertain_tasks', [])}")
            print(f"  无法执行: {execution_plan.get('infeasible_tasks', [])}")
        else:
            print("\n❌ 未触发中断 - 测试失败")
            return
        
        # 2. 测试场景A: 批准执行 (需要新的初始化)
        print("\n" + "=" * 80)
        print("阶段 2A: 用户输入 'Y' (批准)")
        print("=" * 80)
        
        # Re-initialize with new thread_id for approve test
        thread_id_approve = f"{thread_id}-approve"
        result_approve_init = await orchestrator.route(query, thread_id_approve)
        
        if result_approve_init.get("interrupted"):
            resume_result_approve = await orchestrator.resume(
                thread_id=thread_id_approve,  # Use same thread_id as init
                user_input="Y",
                workflow_type=WorkflowType.DEEP_DIVE
            )
            
            print(f"\n批准结果:")
            print(f"  已中止: {resume_result_approve.get('aborted', False)}")
            print(f"  最终消息: {resume_result_approve.get('final_message', 'N/A')[:200]}")
        else:
            print("❌ 未触发中断，跳过批准测试")
        
        # 3. 测试场景B: 中止执行
        print("\n" + "=" * 80)
        print("阶段 2B: 用户输入 'N' (中止)")
        print("=" * 80)
        
        # 需要新的thread_id重新开始
        thread_id_abort = f"{thread_id}-abort"
        result_abort = await orchestrator.route(query, thread_id_abort)
        
        if result_abort.get("interrupted"):
            resume_result_abort = await orchestrator.resume(
                thread_id=thread_id_abort,
                user_input="N",
                workflow_type=WorkflowType.DEEP_DIVE
            )
            
            print(f"\n中止结果:")
            print(f"  已中止: {resume_result_abort.get('aborted', False)}")
            print(f"  最终消息: {resume_result_abort.get('final_message', 'N/A')}")
        
        # 4. 测试场景C: 修改请求
        print("\n" + "=" * 80)
        print("阶段 2C: 用户输入修改请求")
        print("=" * 80)
        
        thread_id_modify = f"{thread_id}-modify"
        result_modify = await orchestrator.route(query, thread_id_modify)
        
        if result_modify.get("interrupted"):
            modification_request = "跳过任务2，使用bgp表执行任务7和8"
            print(f"\n修改请求: {modification_request}")
            
            resume_result_modify = await orchestrator.resume(
                thread_id=thread_id_modify,
                user_input=modification_request,
                workflow_type=WorkflowType.DEEP_DIVE
            )
            
            print(f"\n修改结果:")
            print(f"  已中止: {resume_result_modify.get('aborted', False)}")
            print(f"  已中断（需再审批）: {resume_result_modify.get('interrupted', False)}")
            if resume_result_modify.get("execution_plan"):
                modified_plan = resume_result_modify["execution_plan"]
                print(f"  修改后可行任务: {modified_plan.get('feasible_tasks', [])}")
                print(f"  修改摘要: {modified_plan.get('modification_summary', 'N/A')[:200]}")
        
        print("\n" + "=" * 80)
        print("✅ 所有测试场景完成")
        print("=" * 80)
        
    finally:
        # 清理checkpointer
        await checkpointer_ctx.__aexit__(None, None, None)


if __name__ == "__main__":
    # Windows兼容性
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(test_approval_workflow())
