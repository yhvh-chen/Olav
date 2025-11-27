#!/usr/bin/env python3
"""Test Funnel Debugging with a real network fault.

This script:
1. Modifies R2's GigabitEthernet1 subnet mask from /24 to /30
2. This will break BGP peering between R1 and R2 (subnet mismatch)
3. Runs Deep Dive funnel debugging to diagnose the issue
4. Verifies if it can identify the root cause

Usage:
    uv run python scripts/test_funnel_debug.py
"""

import asyncio
import sys
import selectors
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from olav.core.llm import LLMFactory
from olav.tools.suzieq_tool import SuzieQTool


async def modify_r2_interface():
    """Modify R2's interface to create subnet mismatch using NornirSandbox."""
    print("\n" + "=" * 60)
    print("STEP 1: Modifying R2 GigabitEthernet1 subnet mask")
    print("=" * 60)
    
    try:
        from nornir.core.filter import F
        from nornir_netmiko.tasks import netmiko_send_config
        from olav.execution.backends.nornir_sandbox import NornirSandbox
        
        # Use NornirSandbox which reads from NetBox
        sandbox = NornirSandbox()
        
        # Filter for R2
        r2 = sandbox.nr.filter(F(name="R2"))
        
        if not r2.inventory.hosts:
            print("ERROR: R2 not found in NetBox inventory")
            print("Please ensure R2 has the 'olav-managed' tag in NetBox")
            return False
        
        # Configuration to apply (change /24 to /30)
        config_commands = [
            "interface GigabitEthernet1",
            "ip address 10.1.12.2 255.255.255.252",  # /30 instead of /24
        ]
        
        print(f"Applying configuration to R2:")
        for cmd in config_commands:
            print(f"  {cmd}")
        
        result = r2.run(task=netmiko_send_config, config_commands=config_commands)
        
        for host, host_result in result.items():
            if host_result.failed:
                print(f"ERROR: Failed to configure {host}: {host_result.exception}")
                return False
            print(f"SUCCESS: {host} configured")
        
        return True
        
    except ImportError as e:
        print(f"WARNING: Nornir not fully configured: {e}")
        print("Proceeding with SuzieQ-only diagnosis...")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        print("Proceeding with SuzieQ-only diagnosis...")
        return False


async def run_deep_dive_diagnosis():
    """Run Deep Dive funnel debugging to diagnose the issue."""
    print("\n" + "=" * 60)
    print("STEP 2: Running Deep Dive Funnel Debugging")
    print("=" * 60)
    
    # Import here to avoid circular imports
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from olav.workflows.deep_dive import DeepDiveWorkflow
    from olav.core.settings import settings
    
    # User query simulating the problem report
    user_query = "R1 和 R2 之间的 BGP 邻居无法建立，请排查原因"
    
    print(f"\n问题描述: {user_query}")
    print("\n开始漏斗式诊断...")
    print("-" * 40)
    
    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.postgres_uri
        ) as checkpointer:
            await checkpointer.setup()
            
            # Create workflow
            workflow = DeepDiveWorkflow()
            graph = workflow.build_graph(checkpointer)
            
            # Run the workflow
            config = {
                "configurable": {
                    "thread_id": f"test_funnel_debug_{asyncio.get_event_loop().time()}"
                }
            }
            
            initial_state = {
                "messages": [HumanMessage(content=user_query)],
            }
            
            print("\n=== Workflow Execution ===\n")
            
            async for event in graph.astream(initial_state, config):
                for node_name, node_output in event.items():
                    print(f"\n--- Node: {node_name} ---")
                    
                    # Print topology analysis
                    if "topology" in node_output:
                        topo = node_output["topology"]
                        print(f"受影响设备: {topo.get('affected_devices', [])}")
                        print(f"故障范围: {topo.get('scope', 'unknown')}")
                    
                    # Print diagnosis plan
                    if "diagnosis_plan" in node_output:
                        plan = node_output["diagnosis_plan"]
                        print(f"诊断计划阶段数: {len(plan.get('phases', []))}")
                        for phase in plan.get("phases", []):
                            print(f"  - {phase['name']} ({phase['layer']}): {phase['tables']}")
                    
                    # Print findings
                    if "findings" in node_output and node_output["findings"]:
                        print("发现问题:")
                        for f in node_output["findings"]:
                            print(f"  ⚠️  {f}")
                    
                    # Print realtime verification
                    if "realtime_data" in node_output:
                        print("实时验证数据:")
                        for device, data in node_output["realtime_data"].items():
                            print(f"  {device}: {len(data)} 条命令输出")
                    
                    # Print final message
                    if "messages" in node_output:
                        for msg in node_output["messages"]:
                            if hasattr(msg, "content"):
                                print(f"\n{msg.content[:1500]}...")
            
            print("\n" + "=" * 60)
            print("Deep Dive 诊断完成")
            print("=" * 60)
            
    except Exception as e:
        print(f"ERROR: Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Fall back to direct SuzieQ + CLI diagnosis
        print("\n回退到直接诊断（SuzieQ 历史 + CLI 实时）...")
        await run_hybrid_diagnosis()


async def run_hybrid_diagnosis():
    """Hybrid diagnosis using both SuzieQ (historical) and CLI (real-time)."""
    print("\n" + "=" * 60)
    print("HYBRID DIAGNOSIS: SuzieQ (历史基线) + CLI (实时验证)")
    print("=" * 60)
    
    # Step 1: SuzieQ historical data (baseline)
    print("\n" + "-" * 40)
    print("📊 Phase 1: SuzieQ 历史数据（仅作为参考基线）")
    print("-" * 40)
    
    tool = SuzieQTool()
    suzieq_findings = []
    
    # BGP from SuzieQ
    bgp_result = await tool.execute(table="bgp", method="get", hostname="R1")
    bgp_result2 = await tool.execute(table="bgp", method="get", hostname="R2")
    
    for r in bgp_result.data + bgp_result2.data:
        if r.get("state") == "NotEstd":
            suzieq_findings.append(f"[SuzieQ] BGP {r.get('hostname')} ↔ {r.get('peer')}: NotEstd")
    
    # Interfaces from SuzieQ
    intf_result = await tool.execute(table="interfaces", method="get", hostname="R1")
    intf_result2 = await tool.execute(table="interfaces", method="get", hostname="R2")
    
    for r in intf_result.data + intf_result2.data:
        if "GigabitEthernet1" in str(r.get("ifname", "")):
            state = r.get("state", "unknown")
            admin = r.get("adminState", "unknown")
            ip_list = r.get("ipAddressList", [])
            print(f"  {r.get('hostname')} {r.get('ifname')}: state={state}, admin={admin}, IP={ip_list}")
            if state == "down":
                suzieq_findings.append(f"[SuzieQ] {r.get('hostname')} {r.get('ifname')} 接口 down")
    
    print(f"\nSuzieQ 发现 ({len(suzieq_findings)} 项):")
    for f in suzieq_findings:
        print(f"  ⚠️ {f}")
    
    # Step 2: CLI real-time verification
    print("\n" + "-" * 40)
    print("🔍 Phase 2: CLI 实时验证（实际状态）")
    print("-" * 40)
    
    cli_findings = []
    cli_data = {}
    
    try:
        from olav.tools.nornir_tool import CLITool
        cli_tool = CLITool()
        
        for device in ["R1", "R2"]:
            print(f"\n--- {device} 实时状态 ---")
            cli_data[device] = {}
            
            # Get BGP summary
            try:
                bgp_cli = await cli_tool.execute(device=device, command="show ip bgp summary")
                cli_data[device]["bgp"] = bgp_cli.data
                print(f"BGP Summary: {len(bgp_cli.data)} peers")
                for peer in bgp_cli.data:
                    state = peer.get("state_pfxrcd", peer.get("State", "N/A"))
                    neighbor = peer.get("neighbor", peer.get("Neighbor", "N/A"))
                    print(f"  {neighbor}: {state}")
                    if str(state).lower() in ("idle", "active", "connect"):
                        cli_findings.append(f"[CLI 实时] {device} BGP {neighbor}: {state}")
            except Exception as e:
                print(f"BGP check failed: {e}")
            
            # Get interface status
            try:
                intf_cli = await cli_tool.execute(device=device, command="show ip interface brief")
                cli_data[device]["interfaces"] = intf_cli.data
                for intf in intf_cli.data:
                    if "GigabitEthernet1" in str(intf.get("intf", intf.get("Interface", ""))):
                        status = intf.get("status", intf.get("Status", "N/A"))
                        proto = intf.get("proto", intf.get("Protocol", "N/A"))
                        ip = intf.get("ipaddr", intf.get("IP-Address", "N/A"))
                        print(f"  GigabitEthernet1: IP={ip}, Status={status}, Protocol={proto}")
                        if str(status).lower() in ("down", "administratively down"):
                            cli_findings.append(f"[CLI 实时] {device} GigabitEthernet1: {status}")
            except Exception as e:
                print(f"Interface check failed: {e}")
        
        print(f"\nCLI 实时发现 ({len(cli_findings)} 项):")
        for f in cli_findings:
            print(f"  ✅ {f}")
            
    except Exception as e:
        print(f"CLI 工具初始化失败: {e}")
        print("无法获取实时数据，仅使用 SuzieQ 历史数据。")
    
    # Step 3: Correlate and analyze
    print("\n" + "-" * 40)
    print("🎯 Phase 3: 关联分析")
    print("-" * 40)
    
    all_findings = suzieq_findings + cli_findings
    
    if cli_findings:
        print("✅ CLI 实时数据确认了问题，以下是验证后的发现:")
    else:
        print("⚠️ 无法获取 CLI 实时数据，以下仅为 SuzieQ 历史参考:")
    
    for f in all_findings:
        print(f"  - {f}")
    
    # Use LLM to analyze
    print("\n" + "=" * 60)
    print("AI 根因分析")
    print("=" * 60)
    
    llm = LLMFactory.get_chat_model()
    
    context = f"""
## SuzieQ 历史数据发现
{chr(10).join(f'- {f}' for f in suzieq_findings) if suzieq_findings else '- 无异常'}

## CLI 实时验证发现
{chr(10).join(f'- {f}' for f in cli_findings) if cli_findings else '- 无法获取实时数据'}

## CLI 原始数据
{cli_data}
"""
    
    analysis_prompt = f"""你是网络故障诊断专家。分析以下信息，找出 R1 和 R2 之间 BGP 无法建立的根本原因。

**重要**: CLI 实时数据优先于 SuzieQ 历史数据。

{context}

## 背景信息
- R2 的 GigabitEthernet1 原本配置为 10.1.12.2/24
- 现在被修改为 10.1.12.2/30
- R1 的配置仍然是 10.1.12.1/24

请分析:
1. **数据对比**: SuzieQ 历史数据 vs CLI 实时数据是否一致？
2. **根本原因**: 最可能的故障原因
3. **建议修复**: 具体的修复命令"""
    
    response = await llm.ainvoke([{"role": "user", "content": analysis_prompt}])
    print(response.content)


async def run_suzieq_diagnosis():
    """Direct SuzieQ diagnosis as fallback."""
    print("\n" + "=" * 60)
    print("FALLBACK: Direct SuzieQ Diagnosis")
    print("=" * 60)
    
    tool = SuzieQTool()
    
    # Check BGP status
    print("\n--- BGP 状态检查 ---")
    bgp_result = await tool.execute(
        table="bgp",
        method="get",
        hostname="R1",
    )
    print(f"BGP 邻居状态 (R1):\n{bgp_result.data}")
    
    bgp_result2 = await tool.execute(
        table="bgp",
        method="get",
        hostname="R2",
    )
    print(f"BGP 邻居状态 (R2):\n{bgp_result2.data}")
    
    # Check interface status
    print("\n--- 接口状态检查 ---")
    intf_result = await tool.execute(
        table="interfaces",
        method="get",
        hostname="R1",
    )
    # Filter for GigabitEthernet1
    gi1_data = [r for r in intf_result.data if "GigabitEthernet1" in str(r.get("ifname", ""))]
    print(f"R1 GigabitEthernet1:\n{gi1_data}")
    
    intf_result2 = await tool.execute(
        table="interfaces",
        method="get",
        hostname="R2",
    )
    gi1_data2 = [r for r in intf_result2.data if "GigabitEthernet1" in str(r.get("ifname", ""))]
    print(f"R2 GigabitEthernet1:\n{gi1_data2}")
    
    # Check routes
    print("\n--- 路由检查 ---")
    route_result = await tool.execute(
        table="routes",
        method="get",
        hostname="R1",
    )
    # Filter for 10.1.12.x routes
    r12_routes = [r for r in route_result.data if "10.1.12" in str(r.get("prefix", ""))]
    print(f"R1 10.1.12.x 路由:\n{r12_routes}")
    
    # Analyze results
    print("\n" + "=" * 60)
    print("诊断分析")
    print("=" * 60)
    
    # Prepare context for LLM
    context = f"""
## BGP 状态
R1 BGP: {bgp_result.data}
R2 BGP: {bgp_result2.data}

## 接口状态
R1 GigabitEthernet1: {gi1_data}
R2 GigabitEthernet1: {gi1_data2}

## 路由信息
R1 10.1.12.x routes: {r12_routes}
"""
    
    # Use LLM to analyze
    llm = LLMFactory.get_chat_model()
    
    analysis_prompt = f"""你是网络故障诊断专家。分析以下信息，找出 R1 和 R2 之间 BGP 无法建立的根本原因。

{context}

## 背景信息
- R2 的 GigabitEthernet1 原本配置为 10.1.12.2/24
- 现在被修改为 10.1.12.2/30
- R1 的配置仍然是 10.1.12.1/24

请分析根本原因并给出修复建议。"""
    
    response = await llm.ainvoke([{"role": "user", "content": analysis_prompt}])
    print(response.content)


async def restore_r2_interface():
    """Restore R2's original interface configuration."""
    print("\n" + "=" * 60)
    print("STEP 3: Restoring R2 GigabitEthernet1 original config")
    print("=" * 60)
    
    try:
        from nornir.core.filter import F
        from nornir_netmiko.tasks import netmiko_send_config
        from olav.execution.backends.nornir_sandbox import NornirSandbox
        
        sandbox = NornirSandbox()
        r2 = sandbox.nr.filter(F(name="R2"))
        
        if not r2.inventory.hosts:
            print("R2 not found, skipping restore")
            return
        
        # Restore original configuration
        config_commands = [
            "interface GigabitEthernet1",
            "ip address 10.1.12.2 255.255.255.0",  # Back to /24
        ]
        
        result = r2.run(task=netmiko_send_config, config_commands=config_commands)
        for host, host_result in result.items():
            if host_result.failed:
                print(f"ERROR: Failed to restore {host}")
            else:
                print(f"SUCCESS: {host} restored")
    except Exception as e:
        print(f"ERROR: {e}")


async def main():
    """Main test flow."""
    print("=" * 60)
    print("Funnel Debugging Test - Subnet Mismatch Fault")
    print("=" * 60)
    print("""
测试场景:
- 故障注入: 将 R2 GigabitEthernet1 从 /24 改为 /30
- 预期症状: R1-R2 BGP 邻居无法建立
- 预期诊断: 漏斗式排错应发现子网掩码不匹配

OSI 层分析:
- L1 (物理层): 接口应该是 UP
- L2 (数据链路层): 应该正常
- L3 (网络层): 子网掩码不匹配导致无法通信
- L4+ (传输层): BGP 无法建立 TCP 连接
""")
    
    try:
        # Step 1: Modify configuration (inject fault)
        modified = await modify_r2_interface()
        
        if modified:
            # Wait for changes to take effect
            print("\n等待 10 秒让配置生效...")
            await asyncio.sleep(10)
        
        # Step 2: Run Deep Dive diagnosis
        await run_deep_dive_diagnosis()
        
        # Step 3: Restore original configuration
        if modified:
            restore = input("\n是否恢复原始配置? (y/n): ")
            if restore.lower() == "y":
                await restore_r2_interface()
        
    except KeyboardInterrupt:
        print("\n测试中断")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


# ============================================
# Test Case 2: OSPF MTU Mismatch
# ============================================

async def modify_r2_mtu():
    """Modify R2's GigabitEthernet2 MTU to create OSPF adjacency issue."""
    print("\n" + "=" * 60)
    print("STEP 1: Modifying R2 GigabitEthernet2 MTU (1500 → 1400)")
    print("=" * 60)
    
    try:
        from nornir.core.filter import F
        from nornir_netmiko.tasks import netmiko_send_config
        from olav.execution.backends.nornir_sandbox import NornirSandbox
        
        sandbox = NornirSandbox()
        r2 = sandbox.nr.filter(F(name="R2"))
        
        if not r2.inventory.hosts:
            print("ERROR: R2 not found in NetBox inventory")
            return False
        
        # Configuration to apply (change MTU from 1500 to 1400)
        # This will cause OSPF adjacency to get stuck in ExStart/Exchange
        config_commands = [
            "interface GigabitEthernet2",
            "mtu 1400",  # Mismatch with R4's default 1500
        ]
        
        print(f"Applying configuration to R2:")
        for cmd in config_commands:
            print(f"  {cmd}")
        
        result = r2.run(task=netmiko_send_config, config_commands=config_commands)
        
        for host, host_result in result.items():
            if host_result.failed:
                print(f"ERROR: Failed to configure {host}: {host_result.exception}")
                return False
            print(f"SUCCESS: {host} MTU modified")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False


async def run_ospf_diagnosis():
    """Run diagnosis for R2-R4 OSPF neighbor issue."""
    print("\n" + "=" * 60)
    print("STEP 2: OSPF 邻居诊断")
    print("=" * 60)
    
    user_query = "R2 和 R4 之间的 OSPF 邻居无法建立 Full 状态，请排查原因"
    print(f"\n问题描述: {user_query}")
    
    # Skip Deep Dive workflow (requires HITL approval which blocks)
    # Go directly to hybrid diagnosis for complete results
    print("\n直接执行混合诊断（SuzieQ 历史 + CLI 实时）...")
    await run_ospf_hybrid_diagnosis()


async def run_ospf_hybrid_diagnosis():
    """Hybrid OSPF diagnosis using SuzieQ + CLI."""
    print("\n" + "=" * 60)
    print("OSPF HYBRID DIAGNOSIS: SuzieQ + CLI")
    print("=" * 60)
    
    tool = SuzieQTool()
    
    # Phase 1: SuzieQ historical data
    print("\n" + "-" * 40)
    print("📊 Phase 1: SuzieQ OSPF 历史数据")
    print("-" * 40)
    
    suzieq_findings = []
    
    # OSPF neighbors from SuzieQ
    try:
        ospf_nbr = await tool.execute(table="ospfNbr", method="get", hostname="R2")
        print(f"R2 OSPF Neighbors (SuzieQ): {len(ospf_nbr.data)} 条记录")
        for nbr in ospf_nbr.data:
            state = nbr.get("state", "unknown")
            peer = nbr.get("peerRouterId", nbr.get("peerAddress", "unknown"))
            ifname = nbr.get("ifname", "unknown")
            print(f"  {ifname} → {peer}: state={state}")
            if state not in ("full", "Full", "2-Way", "dr", "bdr"):
                suzieq_findings.append(f"[SuzieQ] OSPF {nbr.get('hostname')} {ifname} → {peer}: {state}")
    except Exception as e:
        print(f"OSPF neighbor query failed: {e}")
    
    # OSPF interfaces from SuzieQ
    try:
        ospf_if = await tool.execute(table="ospfIf", method="get", hostname="R2")
        print(f"\nR2 OSPF Interfaces (SuzieQ): {len(ospf_if.data)} 条记录")
        for intf in ospf_if.data:
            ifname = intf.get("ifname", "unknown")
            state = intf.get("state", "unknown")
            area = intf.get("area", "unknown")
            nbrCount = intf.get("nbrCount", 0)
            print(f"  {ifname}: area={area}, state={state}, neighbors={nbrCount}")
    except Exception as e:
        print(f"OSPF interface query failed: {e}")
    
    # Interfaces (check MTU)
    try:
        interfaces = await tool.execute(table="interfaces", method="get", hostname="R2")
        for intf in interfaces.data:
            if "GigabitEthernet2" in str(intf.get("ifname", "")):
                mtu = intf.get("mtu", "unknown")
                state = intf.get("state", "unknown")
                print(f"\nR2 GigabitEthernet2 (SuzieQ): MTU={mtu}, state={state}")
                if mtu != 1500:
                    suzieq_findings.append(f"[SuzieQ] R2 GigabitEthernet2 MTU={mtu} (非标准)")
    except Exception as e:
        print(f"Interface query failed: {e}")
    
    print(f"\nSuzieQ 发现 ({len(suzieq_findings)} 项):")
    for f in suzieq_findings:
        print(f"  ⚠️ {f}")
    
    # Phase 2: CLI real-time verification
    print("\n" + "-" * 40)
    print("🔍 Phase 2: CLI 实时验证")
    print("-" * 40)
    
    cli_findings = []
    cli_data = {}
    
    try:
        from olav.tools.nornir_tool import CLITool
        cli_tool = CLITool()
        
        for device in ["R2", "R4"]:
            print(f"\n--- {device} 实时状态 ---")
            cli_data[device] = {}
            
            # OSPF neighbor
            try:
                ospf_cli = await cli_tool.execute(device=device, command="show ip ospf neighbor")
                cli_data[device]["ospf_neighbor"] = ospf_cli.data
                print(f"OSPF Neighbors:")
                for nbr in ospf_cli.data:
                    neighbor_id = nbr.get("neighbor_id", nbr.get("Neighbor ID", "N/A"))
                    state = nbr.get("state", nbr.get("State", "N/A"))
                    interface = nbr.get("interface", nbr.get("Interface", "N/A"))
                    print(f"  {neighbor_id} via {interface}: {state}")
                    # Check for stuck states
                    state_lower = str(state).lower()
                    if any(s in state_lower for s in ["exstart", "exchange", "init", "2-way"]):
                        cli_findings.append(f"[CLI 实时] {device} OSPF {neighbor_id}: {state} (未达Full)")
            except Exception as e:
                print(f"OSPF neighbor check failed: {e}")
            
            # Interface MTU
            try:
                intf_cli = await cli_tool.execute(device=device, command="show interfaces GigabitEthernet2")
                cli_data[device]["interface"] = intf_cli.data
                for intf in intf_cli.data:
                    mtu = intf.get("mtu", intf.get("MTU", "N/A"))
                    print(f"GigabitEthernet2 MTU: {mtu}")
                    if mtu and str(mtu) != "1500":
                        cli_findings.append(f"[CLI 实时] {device} GigabitEthernet2 MTU={mtu}")
            except Exception as e:
                print(f"Interface check failed: {e}")
            
            # OSPF interface detail
            try:
                ospf_if_cli = await cli_tool.execute(device=device, command="show ip ospf interface GigabitEthernet2")
                cli_data[device]["ospf_interface"] = ospf_if_cli.data
                print(f"OSPF Interface detail: {len(ospf_if_cli.data)} 条记录")
            except Exception as e:
                print(f"OSPF interface check failed: {e}")
        
        print(f"\nCLI 实时发现 ({len(cli_findings)} 项):")
        for f in cli_findings:
            print(f"  ✅ {f}")
            
    except Exception as e:
        print(f"CLI 工具初始化失败: {e}")
    
    # Phase 3: Analysis
    print("\n" + "-" * 40)
    print("🎯 Phase 3: 关联分析")
    print("-" * 40)
    
    all_findings = suzieq_findings + cli_findings
    
    # Use LLM to analyze
    print("\n" + "=" * 60)
    print("AI 根因分析")
    print("=" * 60)
    
    llm = LLMFactory.get_chat_model()
    
    context = f"""
## SuzieQ 历史数据发现
{chr(10).join(f'- {f}' for f in suzieq_findings) if suzieq_findings else '- 无异常'}

## CLI 实时验证发现
{chr(10).join(f'- {f}' for f in cli_findings) if cli_findings else '- 未发现异常'}

## CLI 原始数据
{cli_data}
"""
    
    analysis_prompt = f"""你是网络故障诊断专家。分析以下信息，找出 R2 和 R4 之间 OSPF 邻居无法建立 Full 状态的根本原因。

**重要**: CLI 实时数据优先于 SuzieQ 历史数据。

{context}

## 背景信息
- R2 的 GigabitEthernet2 MTU 已从 1500 改为 1400
- R4 的 GigabitEthernet2 MTU 仍然是 1500
- OSPF 在 Database Description (DBD) 交换阶段会检查 MTU

请分析:
1. **OSPF 邻接过程**: 当前卡在哪个状态？
2. **根本原因**: MTU 不匹配如何影响 OSPF？
3. **建议修复**: 具体的修复命令（两种方案：统一 MTU 或 忽略 MTU）"""
    
    response = await llm.ainvoke([{"role": "user", "content": analysis_prompt}])
    print(response.content)


async def restore_r2_mtu():
    """Restore R2's GigabitEthernet2 MTU to default."""
    print("\n" + "=" * 60)
    print("STEP 3: Restoring R2 GigabitEthernet2 MTU")
    print("=" * 60)
    
    try:
        from nornir.core.filter import F
        from nornir_netmiko.tasks import netmiko_send_config
        from olav.execution.backends.nornir_sandbox import NornirSandbox
        
        sandbox = NornirSandbox()
        r2 = sandbox.nr.filter(F(name="R2"))
        
        if not r2.inventory.hosts:
            print("R2 not found, skipping restore")
            return
        
        # Restore original MTU
        config_commands = [
            "interface GigabitEthernet2",
            "mtu 1500",  # Back to default
        ]
        
        result = r2.run(task=netmiko_send_config, config_commands=config_commands)
        for host, host_result in result.items():
            if host_result.failed:
                print(f"ERROR: Failed to restore {host}")
            else:
                print(f"SUCCESS: {host} MTU restored to 1500")
    except Exception as e:
        print(f"ERROR: {e}")


async def main_ospf_mtu_test():
    """Main test flow for OSPF MTU mismatch."""
    print("=" * 60)
    print("Funnel Debugging Test - OSPF MTU Mismatch")
    print("=" * 60)
    print("""
测试场景:
- 故障注入: 将 R2 GigabitEthernet2 MTU 从 1500 改为 1400
- 预期症状: R2-R4 OSPF 邻居卡在 ExStart/Exchange 状态
- 预期诊断: 漏斗式排错应发现 MTU 不匹配

OSI 层分析:
- L1 (物理层): 接口应该是 UP
- L2 (数据链路层): 应该正常
- L3 (网络层): OSPF DBD 包含接口 MTU，不匹配会拒绝建立邻接
- L4+ (应用层): OSPF 协议层面的 MTU 检查

OSPF 邻接状态机:
  Down → Init → 2-Way → ExStart → Exchange → Loading → Full
                              ↑
                        MTU 不匹配会卡在这里！
""")
    
    try:
        # Step 1: Modify MTU
        modified = await modify_r2_mtu()
        
        if modified:
            # Wait for OSPF to detect the change
            print("\n等待 15 秒让 OSPF 检测到变化...")
            await asyncio.sleep(15)
        
        # Step 2: Run diagnosis
        await run_ospf_diagnosis()
        
        # Step 3: Restore
        if modified:
            restore = input("\n是否恢复原始 MTU? (y/n): ")
            if restore.lower() == "y":
                await restore_r2_mtu()
        
    except KeyboardInterrupt:
        print("\n测试中断")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


async def main_menu():
    """Main menu for test case selection."""
    print("=" * 60)
    print("OLAV Funnel Debugging Test Suite")
    print("=" * 60)
    print("""
选择测试用例:
  1. BGP 子网掩码不匹配 (R1-R2)
  2. OSPF MTU 不匹配 (R2-R4)
  3. 退出
""")
    
    choice = input("请选择 (1/2/3): ").strip()
    
    if choice == "1":
        await main()
    elif choice == "2":
        await main_ospf_mtu_test()
    elif choice == "3":
        print("退出")
        return
    else:
        print("无效选择")


if __name__ == "__main__":
    # Fix for Windows asyncio with psycopg
    if sys.platform == "win32":
        # Use SelectorEventLoop instead of ProactorEventLoop
        selector = selectors.SelectSelector()
        loop = asyncio.SelectorEventLoop(selector)
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main_menu())
        finally:
            loop.close()
    else:
        asyncio.run(main_menu())
