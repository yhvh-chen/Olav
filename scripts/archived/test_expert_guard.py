"""Test Expert Mode Guard with various query types.

This script tests the two-layer filtering mechanism:
- Layer 1: Relevance Filter (fault_diagnosis vs simple_query/config_change/off_topic)
- Layer 2: Sufficiency Check (symptom + device required)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from olav.core.llm import LLMFactory
from olav.modes.expert.guard import (
    ExpertModeGuard,
    QueryType,
    SymptomType,
)


# Test cases: (query, expected_type, expected_sufficient)
TEST_CASES = [
    # Fault diagnosis - sufficient
    ("R3 无法访问 10.0.100.100", QueryType.FAULT_DIAGNOSIS, True),
    ("R1 和 R2 之间 BGP 邻居 down", QueryType.FAULT_DIAGNOSIS, True),
    ("从 R1 ping R4 不通", QueryType.FAULT_DIAGNOSIS, True),
    ("R2 的 OSPF 邻居丢失了", QueryType.FAULT_DIAGNOSIS, True),
    
    # Fault diagnosis - insufficient (missing device or symptom)
    ("网络有问题", QueryType.FAULT_DIAGNOSIS, False),
    ("BGP 邻居为什么 down", QueryType.FAULT_DIAGNOSIS, False),
    ("接口报错", QueryType.FAULT_DIAGNOSIS, False),
    
    # Simple query - should redirect to Standard Mode
    ("查询 R1 接口状态", QueryType.SIMPLE_QUERY, None),
    ("显示所有 BGP 邻居", QueryType.SIMPLE_QUERY, None),
    ("R2 有哪些路由", QueryType.SIMPLE_QUERY, None),
    ("列出所有设备", QueryType.SIMPLE_QUERY, None),
    
    # Config change - should redirect to Standard Mode
    ("配置 OSPF area 0", QueryType.CONFIG_CHANGE, None),
    ("修改 BGP neighbor 的密码", QueryType.CONFIG_CHANGE, None),
    ("添加一条 ACL 规则", QueryType.CONFIG_CHANGE, None),
    
    # Off-topic - should reject
    ("今天天气如何", QueryType.OFF_TOPIC, None),
    ("写一首关于网络的诗", QueryType.OFF_TOPIC, None),
    ("帮我算一下 1+1", QueryType.OFF_TOPIC, None),
]


async def test_guard():
    """Run guard tests."""
    
    print("=" * 70)
    print("Expert Mode Guard Test")
    print("=" * 70)
    
    # Initialize
    llm = LLMFactory.get_chat_model(json_mode=True)
    guard = ExpertModeGuard(llm=llm)
    
    results = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
    }
    
    for query, expected_type, expected_sufficient in TEST_CASES:
        try:
            print(f"\n{'─' * 70}")
            print(f"Query: {query}")
            print(f"Expected: type={expected_type.value}, sufficient={expected_sufficient}")
            
            result = await guard.check(query)
            
            # Check type
            type_match = result.query_type == expected_type
            
            # Check sufficiency (only for fault_diagnosis)
            if expected_type == QueryType.FAULT_DIAGNOSIS:
                sufficient_match = result.is_sufficient == expected_sufficient
            else:
                # For non-fault queries, sufficiency doesn't matter
                sufficient_match = True
            
            passed = type_match and sufficient_match
            
            # Print result
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"Result:   type={result.query_type.value}, sufficient={result.is_sufficient}")
            print(f"Status:   {status}")
            
            if result.context:
                print(f"Context:  symptom={result.context.symptom}, "
                      f"type={result.context.symptom_type.value if result.context.symptom_type else 'N/A'}")
                print(f"          source={result.context.source_device}, "
                      f"target={result.context.target_device}")
            
            if not result.is_sufficient and result.clarification_prompt:
                print(f"Clarify:  {result.clarification_prompt}")
            
            if result.redirect_mode:
                print(f"Redirect: {result.redirect_mode}")
            
            if passed:
                results["passed"] += 1
            else:
                results["failed"] += 1
                print(f"MISMATCH: expected type={expected_type.value}, got {result.query_type.value}")
                if expected_type == QueryType.FAULT_DIAGNOSIS:
                    print(f"          expected sufficient={expected_sufficient}, got {result.is_sufficient}")
            
        except Exception as e:
            print(f"ERROR: {e}")
            results["errors"] += 1
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total:   {len(TEST_CASES)}")
    print(f"Passed:  {results['passed']}")
    print(f"Failed:  {results['failed']}")
    print(f"Errors:  {results['errors']}")
    print("=" * 70)
    
    return results["failed"] == 0 and results["errors"] == 0


if __name__ == "__main__":
    success = asyncio.run(test_guard())
    sys.exit(0 if success else 1)
