#!/usr/bin/env python
"""Test hybrid search on diagnosis knowledge base."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from olav.tools.kb_tools import kb_search

# Test semantic similarity search - using different wording
test_queries = [
    "BGP 邻居断开",  # Similar meaning, different words
    "路由协议连接问题",  # More abstract
    "neighbor session down",  # English query
    "R1 无法和 R2 通信",  # Device-specific
]

print("=" * 60)
print("Hybrid Search Test (Keyword + Vector)")
print("=" * 60)

for query in test_queries:
    print(f"\nQuery: {query}")
    results = kb_search.invoke({"query": query, "size": 3})
    if results:
        for r in results:
            print(f"  ✓ {r['case_id']}")
            print(f"    Root cause: {r['root_cause'][:60]}...")
            print(f"    Score: {r['similarity_score']}, Layer: {r.get('root_cause_layer')}")
    else:
        print("  (No results)")
