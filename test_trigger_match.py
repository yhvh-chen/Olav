"""Test intent classification and validation for delete command."""
import asyncio
import os


async def main():
    # Import settings first to check env vars
    from config.settings import settings

    print(f"LLM API Key prefix: {settings.llm_api_key[:10]}...")
    print(f"OLAV_USE_DYNAMIC_ROUTER env: {os.getenv('OLAV_USE_DYNAMIC_ROUTER', 'not set')}")

    # Create orchestrator
    from olav.agents.root_agent_orchestrator import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(checkpointer=None, expert_mode=False)
    print(f"use_dynamic_router: {orchestrator.use_dynamic_router}")
    print(f"dynamic_router: {orchestrator.dynamic_router}")

    # If dynamic router exists, try to build index
    if orchestrator.dynamic_router:
        await orchestrator.initialize()
        print("Dynamic router initialized successfully")

    # Test classification
    query = "delete lo11"
    intent = await orchestrator.classify_intent(query)
    print(f'classify_intent("{query}") = {intent}')

    # Test validation
    workflow = orchestrator.workflows[intent]
    is_valid, reason = await workflow.validate_input(query)
    print(f'validate_input("{query}") = ({is_valid}, "{reason}")')

    if is_valid:
        print("✅ Query will be routed to DeviceExecutionWorkflow correctly!")
    else:
        print("❌ Query will be downgraded to QUERY_DIAGNOSTIC")

    # Test another query
    print()
    query2 = "add interface loopback 100"
    intent2 = await orchestrator.classify_intent(query2)
    print(f'classify_intent("{query2}") = {intent2}')

    workflow2 = orchestrator.workflows[intent2]
    is_valid2, reason2 = await workflow2.validate_input(query2)
    print(f'validate_input("{query2}") = ({is_valid2}, "{reason2}")')


if __name__ == "__main__":
    asyncio.run(main())
