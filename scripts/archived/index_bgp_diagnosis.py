#!/usr/bin/env python
"""Index the recent BGP diagnosis test report to knowledge base with embeddings.

This script creates a DiagnosisReport from the recent BGP shutdown test
and indexes it with vector embeddings for semantic search.

Usage:
    uv run python scripts/index_bgp_diagnosis.py
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    from olav.models.diagnosis_report import DiagnosisReport, DeviceSummary
    from olav.tools.kb_tools import kb_index_report, kb_stats
    
    # Create report from the BGP shutdown test (Dec 4, 2025)
    report = DiagnosisReport(
        report_id=f"diag-bgp-shutdown-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        timestamp=datetime.now(timezone.utc).isoformat(),  # Must be string
        fault_description="R1 的 BGP 邻居 10.1.12.2 (R2) 无法建立连接，用户报告无法访问远端网络",
        source="R1",
        destination="R2",
        fault_path=["R1", "R2"],
        root_cause="BGP neighbor 被管理员手动 shutdown，导致邻居关系无法建立",
        root_cause_device="R1",
        root_cause_layer="L3",
        confidence=0.95,
        evidence_chain=[
            "show ip bgp summary 显示 neighbor 10.1.12.2 状态为 Idle (Admin)",
            "syslog 记录显示 BGP peer reset due to administrative shutdown",
            "running-config 确认存在 neighbor 10.1.12.2 shutdown 配置",
            "邻居 R2 侧 BGP 状态为 Active，等待对端连接",
        ],
        device_summaries={
            "R1": DeviceSummary(
                device="R1",
                status="faulty",
                layer_findings={
                    "L3": [
                        "BGP neighbor 10.1.12.2 configured with 'shutdown'",
                        "Neighbor state: Idle (Admin)",
                        "No BGP prefixes exchanged",
                    ]
                },
                confidence=0.95,
            ),
            "R2": DeviceSummary(
                device="R2",
                status="waiting",
                layer_findings={
                    "L3": [
                        "BGP neighbor 10.1.12.1 state: Active",
                        "Waiting for peer connection",
                    ]
                },
                confidence=0.85,
            ),
        },
        recommended_action="移除 R1 上的 neighbor shutdown 配置: no neighbor 10.1.12.2 shutdown",
        resolution_applied=True,
        resolution_result="执行 no neighbor 10.1.12.2 shutdown 后，BGP 邻居在 30 秒内恢复正常",
        tags=["bgp", "shutdown", "administrative", "neighbor"],
        affected_protocols=["bgp"],
        affected_layers=["L3"],
    )
    
    logger.info(f"Created diagnosis report: {report.report_id}")
    logger.info(f"  Fault: {report.fault_description}")
    logger.info(f"  Root Cause: {report.root_cause}")
    
    # Index with embeddings
    logger.info("Indexing report with embeddings...")
    success = await kb_index_report(report)
    
    if success:
        logger.info("✅ Report indexed successfully!")
        
        # Show stats
        stats = kb_stats()
        logger.info(f"KB stats: {stats}")
    else:
        logger.error("❌ Failed to index report")


if __name__ == "__main__":
    asyncio.run(main())
