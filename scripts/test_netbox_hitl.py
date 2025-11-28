#!/usr/bin/env python
"""Test script for NetBoxManagement HITL (Human-in-the-Loop) workflow.

This script verifies that:
1. NetBoxManagement workflow triggers HITL interrupt for write operations
2. The interrupted state returns interrupt metadata
3. The resume() method correctly continues the workflow after approval
"""
import asyncio
import sys
import time

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def test_netbox_hitl():
    """Test NetBox HITL interrupt and resume flow."""
    from rich.console import Console
    from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
    from olav.workflows.base import WorkflowType
    
    console = Console()
    console.print("[bold cyan]Testing NetBoxManagement HITL Flow[/bold cyan]\n")
    
    # Initialize orchestrator
    console.print("1. Initializing orchestrator...")
    orchestrator, stateful_graph, stateless_graph, checkpointer_mgr = await create_workflow_orchestrator(
        expert_mode=False  # NetBox workflow doesn't need expert mode
    )
    console.print("[green]✅ Orchestrator initialized[/green]\n")
    
    # Test query - Add a new device (write operation)
    query = "在 NetBox 中添加一台新设备 Test-Switch-01"
    thread_id = f"test-netbox-hitl-{int(time.time())}"
    
    console.print(f"2. Executing query: {query}")
    console.print(f"   Thread ID: {thread_id}\n")
    
    # Route to workflow
    result = await orchestrator.route(query, thread_id)
    
    console.print("[bold]Workflow Result:[/bold]")
    console.print(f"   - workflow_type: {result.get('workflow_type')}")
    console.print(f"   - interrupted: {result.get('interrupted')}")
    console.print(f"   - next_node: {result.get('next_node')}")
    
    # Get final message
    final_msg = result.get("final_message")
    if final_msg:
        console.print(f"   - final_message: {final_msg[:200]}...")
    
    # Check if workflow was routed correctly
    workflow_type = result.get("workflow_type", "").upper()
    if workflow_type != "NETBOX_MANAGEMENT":
        console.print(f"\n[red]❌ Wrong workflow type: {workflow_type} (expected NETBOX_MANAGEMENT)[/red]")
        return
    
    if result.get("interrupted"):
        console.print("\n[yellow]⏸️ Workflow interrupted for HITL approval![/yellow]")
        console.print("[green]✅ HITL interrupt triggered correctly![/green]")
        
        # Show interrupt details
        inner_result = result.get("result", {})
        if inner_result:
            api_endpoint = inner_result.get("api_endpoint")
            operation_plan = inner_result.get("operation_plan")
            approval_status = inner_result.get("approval_status")
            console.print(f"\n   API Endpoint: {api_endpoint}")
            console.print(f"   Operation Plan: {operation_plan}")
            console.print(f"   Approval Status: {approval_status}")
        
        # Test resume with "Y" approval
        console.print("\n3. Testing resume with 'Y' approval...")
        
        resume_result = await orchestrator.resume(
            thread_id=thread_id,
            user_input="Y",
            workflow_type=WorkflowType.NETBOX_MANAGEMENT,
        )
        
        console.print("[bold]Resume Result:[/bold]")
        console.print(f"   - interrupted: {resume_result.get('interrupted')}")
        console.print(f"   - aborted: {resume_result.get('aborted')}")
        
        inner_resume = resume_result.get("result", {})
        if inner_resume:
            execution_result = inner_resume.get("execution_result")
            console.print(f"   - execution_result: {execution_result}")
        
        final_msg = resume_result.get("final_message")
        if final_msg:
            console.print(f"   - final_message: {final_msg[:200]}...")
        
        if not resume_result.get("interrupted") and not resume_result.get("aborted"):
            console.print("\n[green]✅ HITL test PASSED! Workflow completed after approval.[/green]")
        elif resume_result.get("aborted"):
            console.print("\n[yellow]⚠️ Workflow was aborted (may be expected if Y wasn't recognized).[/yellow]")
        else:
            console.print("\n[yellow]⚠️ Workflow still interrupted (may need more approvals).[/yellow]")
    else:
        console.print("\n[red]❌ HITL test FAILED: Workflow was NOT interrupted![/red]")
        console.print("   Check hitl_approval_node implementation.")
        
        # Print more details for debugging
        if final_msg:
            console.print(f"\n   Full response:\n{final_msg}")
    
    # Cleanup
    if hasattr(checkpointer_mgr, '__aexit__'):
        await checkpointer_mgr.__aexit__(None, None, None)
    elif hasattr(checkpointer_mgr, '__exit__'):
        checkpointer_mgr.__exit__(None, None, None)
    
    console.print("\n[dim]Test completed.[/dim]")


async def test_netbox_yolo_mode():
    """Test NetBox workflow in YOLO mode (auto-approve)."""
    from rich.console import Console
    from config.settings import AgentConfig
    from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
    
    console = Console()
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]Testing NetBoxManagement YOLO Mode (Auto-approve)[/bold cyan]\n")
    
    # Enable YOLO mode
    original_yolo = AgentConfig.YOLO_MODE
    AgentConfig.YOLO_MODE = True
    console.print("[yellow]YOLO mode enabled - all approvals will be auto-accepted[/yellow]\n")
    
    try:
        # Initialize orchestrator
        console.print("1. Initializing orchestrator...")
        orchestrator, stateful_graph, stateless_graph, checkpointer_mgr = await create_workflow_orchestrator(
            expert_mode=False
        )
        console.print("[green]✅ Orchestrator initialized[/green]\n")
        
        # Test query
        query = "在 NetBox 中添加一台新设备 YOLO-Test-Switch"
        thread_id = f"test-netbox-yolo-{int(time.time())}"
        
        console.print(f"2. Executing query: {query}")
        console.print(f"   Thread ID: {thread_id}\n")
        
        # Route to workflow
        result = await orchestrator.route(query, thread_id)
        
        console.print("[bold]Workflow Result:[/bold]")
        console.print(f"   - workflow_type: {result.get('workflow_type')}")
        console.print(f"   - interrupted: {result.get('interrupted')}")
        
        if result.get("interrupted"):
            console.print("\n[red]❌ YOLO test FAILED: Workflow was interrupted (should auto-approve)[/red]")
        else:
            console.print("\n[green]✅ YOLO test PASSED! Workflow completed without interruption.[/green]")
        
        # Cleanup
        if hasattr(checkpointer_mgr, '__aexit__'):
            await checkpointer_mgr.__aexit__(None, None, None)
        elif hasattr(checkpointer_mgr, '__exit__'):
            checkpointer_mgr.__exit__(None, None, None)
            
    finally:
        # Restore YOLO mode
        AgentConfig.YOLO_MODE = original_yolo
    
    console.print("\n[dim]YOLO test completed.[/dim]")


if __name__ == "__main__":
    asyncio.run(test_netbox_hitl())
    # Uncomment to also test YOLO mode:
    # asyncio.run(test_netbox_yolo_mode())
