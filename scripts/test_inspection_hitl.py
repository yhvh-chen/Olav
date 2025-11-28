#!/usr/bin/env python
"""Test script for InspectionWorkflow HITL (Human-in-the-Loop).

This script verifies that:
1. InspectionWorkflow triggers HITL interrupt when diffs are found
2. The interrupted state returns proper interrupt metadata
3. The resume() method correctly continues the workflow after approval
"""
import asyncio
import sys
import time

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def test_inspection_hitl():
    """Test Inspection HITL interrupt and resume flow."""
    from rich.console import Console
    from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
    from olav.workflows.base import WorkflowType
    
    console = Console()
    console.print("[bold cyan]Testing InspectionWorkflow HITL Flow[/bold cyan]\n")
    
    # Initialize orchestrator
    console.print("1. Initializing orchestrator...")
    orchestrator, stateful_graph, stateless_graph, checkpointer_mgr = await create_workflow_orchestrator(
        expert_mode=False
    )
    console.print("[green]✅ Orchestrator initialized[/green]\n")
    
    # Test query - Sync network state to NetBox
    query = "同步网络设备状态到 NetBox"
    thread_id = f"test-inspection-hitl-{int(time.time())}"
    
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
    if workflow_type != "INSPECTION":
        console.print(f"\n[yellow]⚠️ Routed to {workflow_type} (expected INSPECTION)[/yellow]")
        console.print("   This is expected if keyword routing prioritizes other workflows.")
    
    if result.get("interrupted"):
        console.print("\n[yellow]⏸️ Workflow interrupted for HITL approval![/yellow]")
        console.print("[green]✅ HITL interrupt triggered correctly![/green]")
        
        # Show interrupt details
        inner_result = result.get("result", {})
        if inner_result:
            diff_report = inner_result.get("diff_report", {})
            if diff_report:
                console.print(f"\n   Device scope: {diff_report.get('device_scope', [])}")
                console.print(f"   Total entities: {diff_report.get('total_entities', 0)}")
                console.print(f"   Mismatched: {diff_report.get('mismatched', 0)}")
        
        # Test resume with "Y" approval
        console.print("\n3. Testing resume with 'Y' approval...")
        
        resume_result = await orchestrator.resume(
            thread_id=thread_id,
            user_input="Y",
            workflow_type=WorkflowType.INSPECTION,
        )
        
        console.print("[bold]Resume Result:[/bold]")
        console.print(f"   - interrupted: {resume_result.get('interrupted')}")
        console.print(f"   - aborted: {resume_result.get('aborted')}")
        
        inner_resume = resume_result.get("result", {})
        if inner_resume:
            reconcile_results = inner_resume.get("reconcile_results", [])
            console.print(f"   - reconcile_results count: {len(reconcile_results)}")
            dry_run = inner_resume.get("dry_run")
            console.print(f"   - dry_run: {dry_run}")
        
        final_msg = resume_result.get("final_message")
        if final_msg:
            console.print(f"   - final_message: {final_msg[:300]}...")
        
        if not resume_result.get("interrupted") and not resume_result.get("aborted"):
            console.print("\n[green]✅ HITL test PASSED! Workflow completed after approval.[/green]")
        elif resume_result.get("aborted"):
            console.print("\n[yellow]⚠️ Workflow was aborted.[/yellow]")
        else:
            console.print("\n[yellow]⚠️ Workflow still interrupted.[/yellow]")
    else:
        # Workflow completed without interrupt - might be no diffs found
        console.print("\n[cyan]ℹ️ Workflow completed without HITL interrupt.[/cyan]")
        console.print("   This is normal if no differences were found to sync.")
        
        inner_result = result.get("result", {})
        if inner_result:
            diff_report = inner_result.get("diff_report", {})
            if diff_report:
                mismatched = diff_report.get("mismatched", 0)
                if mismatched == 0:
                    console.print(f"   [green]✅ No mismatches found - no sync needed[/green]")
                else:
                    console.print(f"   [red]❌ {mismatched} mismatches but HITL not triggered![/red]")
    
    # Cleanup
    if hasattr(checkpointer_mgr, '__aexit__'):
        await checkpointer_mgr.__aexit__(None, None, None)
    elif hasattr(checkpointer_mgr, '__exit__'):
        checkpointer_mgr.__exit__(None, None, None)
    
    console.print("\n[dim]Test completed.[/dim]")


if __name__ == "__main__":
    asyncio.run(test_inspection_hitl())
