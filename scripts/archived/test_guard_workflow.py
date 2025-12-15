"""Test Expert Mode workflow with Guard integration."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from olav.modes.expert.workflow import ExpertModeWorkflow


async def test():
    """Test Guard integration with workflow."""
    
    workflow = ExpertModeWorkflow(enable_guard=True, enable_phase2=True)
    
    # Test 1: Valid fault diagnosis
    print("=" * 60)
    print("Test 1: Valid fault diagnosis query")
    result = await workflow.run(
        "R3 无法访问 10.0.100.100",
        path_devices=["R3", "R1", "R2"]
    )
    print(f"Guard passed: {result.guard_result.is_fault_diagnosis if result.guard_result else 'N/A'}")
    if result.diagnosis_context:
        print(f"Diagnosis context:")
        print(f"  - symptom: {result.diagnosis_context.symptom}")
        print(f"  - type: {result.diagnosis_context.symptom_type.value}")
        print(f"  - source: {result.diagnosis_context.source_device}")
        print(f"  - target: {result.diagnosis_context.target_device}")
    print(f"Redirected: {result.redirected}")
    print(f"Clarification needed: {result.clarification_needed}")
    print(f"Success: {result.success}")
    print(f"Root cause found: {result.root_cause_found}")
    if result.root_cause:
        print(f"Root cause: {result.root_cause[:100]}...")
    
    # Test 2: Simple query - should redirect
    print()
    print("=" * 60)
    print("Test 2: Simple query (should redirect)")
    result2 = await workflow.run("查询 R1 接口状态")
    print(f"Guard passed: {result2.guard_result.is_fault_diagnosis if result2.guard_result else 'N/A'}")
    print(f"Redirected: {result2.redirected}")
    print(f"Redirect mode: {result2.redirect_mode}")
    print(f"Message: {result2.final_report}")
    
    # Test 3: Insufficient info - should ask for clarification
    print()
    print("=" * 60)
    print("Test 3: Insufficient info (should clarify)")
    result3 = await workflow.run("网络有问题")
    print(f"Guard passed: {result3.guard_result.is_fault_diagnosis if result3.guard_result else 'N/A'}")
    print(f"Clarification needed: {result3.clarification_needed}")
    print(f"Missing info: {result3.missing_info}")
    print(f"Clarification prompt: {result3.clarification_prompt}")
    
    print()
    print("=" * 60)
    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(test())
