#!/usr/bin/env python
"""Test script for BGP diagnosis with Supervisor-Driven workflow."""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_diagnosis():
    from olav.workflows.supervisor_driven import create_supervisor_driven_workflow, create_initial_state
    
    # 创建 workflow
    workflow = create_supervisor_driven_workflow()
    
    # 创建初始状态
    state = create_initial_state(
        query="R1和R2之间的BGP邻居关系断开了，请诊断原因",
        path_devices=["R1", "R2"],
        max_rounds=3
    )
    
    print("=" * 60)
    print("=== Starting Supervisor-Driven Diagnosis ===")
    print("=" * 60)
    print(f"Query: {state['query']}")
    print(f"Path Devices: {state['path_devices']}")
    print()
    
    # 运行 workflow
    async for event in workflow.astream(state):
        for key, value in event.items():
            if "messages" in value:
                for msg in value["messages"]:
                    content = msg.content
                    print(f"\n[{key}]")
                    print("-" * 40)
                    if len(content) > 1000:
                        print(content[:1000] + "...")
                    else:
                        print(content)
                    print()
    
    print("=" * 60)
    print("=== Diagnosis Complete ===")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_diagnosis())
