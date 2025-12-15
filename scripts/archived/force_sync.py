#!/usr/bin/env python
"""
Force Sync - 强制同步网络状态到 NetBox

网络设备是 Source of Truth，NetBox 必须与网络保持一致。

同步范围：
1. 接口 (interfaces) - 创建/删除/更新
2. IP 地址 (ip_addresses) - 创建/删除/更新
3. 设备信息 (device) - 更新 serial, version, platform
4. VLAN (vlans) - 创建/删除/更新

强制一致性规则：
- 网络有 + NetBox 没有 → 在 NetBox 创建
- 网络没有 + NetBox 有 → 从 NetBox 删除 (HITL)
- 字段不一致 → 更新 NetBox 以匹配网络

Usage:
    uv run python scripts/force_sync.py --device R1          # 同步单个设备 (dry run)
    uv run python scripts/force_sync.py --device R1 --apply  # 真正执行
    uv run python scripts/force_sync.py --all                # 同步所有设备
    uv run python scripts/force_sync.py --device R1 --yes    # 跳过 HITL 确认
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Setup path and event loop
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from olav.sync.models import (
    DiffResult,
    DiffSeverity,
    DiffSource,
    EntityType,
    ReconcileAction,
    ReconciliationReport,
)
from olav.sync.reconciler import NetBoxReconciler
from olav.tools.netbox_tool import NetBoxAPITool
from olav.tools.suzieq_parquet_tool import suzieq_query

console = Console()


class ForceSyncEngine:
    """
    强制同步引擎 - 确保 NetBox 与网络完全一致
    
    网络设备是唯一真理来源 (Single Source of Truth)
    """

    def __init__(
        self,
        netbox: NetBoxAPITool | None = None,
        dry_run: bool = True,
        skip_hitl: bool = False,
    ) -> None:
        self.netbox = netbox or NetBoxAPITool()
        self.dry_run = dry_run
        self.skip_hitl = skip_hitl
        
        # Stats
        self.stats = {
            "interfaces_created": 0,
            "interfaces_deleted": 0,
            "interfaces_updated": 0,
            "ips_created": 0,
            "ips_deleted": 0,
            "ips_updated": 0,
            "devices_updated": 0,
            "errors": 0,
            "skipped": 0,
        }

    async def sync_device(self, device: str) -> ReconciliationReport:
        """同步单个设备的所有数据到 NetBox"""
        console.print(f"\n[bold blue]🔄 开始同步设备: {device}[/bold blue]")
        
        report = ReconciliationReport(device_scope=[device])
        
        # 1. 同步接口
        await self._sync_interfaces(device, report)
        
        # 2. 同步 IP 地址
        await self._sync_ip_addresses(device, report)
        
        # 3. 同步设备信息
        await self._sync_device_info(device, report)
        
        return report

    async def _sync_interfaces(self, device: str, report: ReconciliationReport) -> None:
        """同步接口 - 强制 NetBox 与网络一致"""
        console.print("\n[cyan]📡 同步接口...[/cyan]")
        
        # 获取 SuzieQ 接口数据
        sq_result = await suzieq_query.ainvoke({
            "table": "interfaces",
            "method": "get",
            "hostname": device,
        })
        
        # 获取 NetBox 设备 ID
        device_result = await self.netbox.execute(
            path="/api/dcim/devices/",
            method="GET",
            params={"name": device},
        )
        
        if device_result.error or not device_result.data:
            console.print(f"[red]❌ 设备 {device} 未在 NetBox 中找到[/red]")
            self.stats["errors"] += 1
            return
        
        device_id = device_result.data[0]["id"]
        
        # 获取 NetBox 接口
        nb_result = await self.netbox.execute(
            path="/api/dcim/interfaces/",
            method="GET",
            params={"device_id": device_id},
        )
        
        if nb_result.error:
            console.print(f"[red]❌ 获取 NetBox 接口失败: {nb_result.error}[/red]")
            return
        
        # 解析数据
        network_interfaces = self._parse_suzieq_interfaces(sq_result, device)
        netbox_interfaces = {iface["name"]: iface for iface in (nb_result.data or [])}
        
        console.print(f"  网络接口: {len(network_interfaces)} 个")
        console.print(f"  NetBox 接口: {len(netbox_interfaces)} 个")
        
        # 对比并同步
        all_names = set(network_interfaces.keys()) | set(netbox_interfaces.keys())
        
        for ifname in sorted(all_names):
            net_data = network_interfaces.get(ifname)
            nb_data = netbox_interfaces.get(ifname)
            
            if net_data and not nb_data:
                # 网络有，NetBox 没有 → 创建
                await self._create_interface(device, device_id, ifname, net_data, report)
                
            elif nb_data and not net_data:
                # NetBox 有，网络没有 → 删除 (需确认)
                await self._delete_interface(device, nb_data, report)
                
            else:
                # 两边都有 → 对比字段
                await self._update_interface(device, ifname, net_data, nb_data, report)

    async def _create_interface(
        self,
        device: str,
        device_id: int,
        ifname: str,
        net_data: dict[str, Any],
        report: ReconciliationReport,
    ) -> None:
        """在 NetBox 创建接口"""
        console.print(f"  [green]+ 创建接口: {ifname}[/green]")
        
        report.missing_in_netbox += 1
        report.add_diff(DiffResult(
            entity_type=EntityType.INTERFACE,
            device=device,
            field="existence",
            network_value="present",
            netbox_value="missing",
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
            identifier=ifname,
            additional_context=net_data,
        ))
        
        if self.dry_run:
            console.print(f"    [dim](dry run - 不会真正创建)[/dim]")
            return
        
        # 确定接口类型
        interface_type = self._map_interface_type(ifname, net_data.get("type"))
        
        payload = {
            "device": device_id,
            "name": ifname,
            "type": interface_type,
            "enabled": net_data.get("adminState", "up") == "up",
        }
        
        if net_data.get("mtu"):
            payload["mtu"] = net_data["mtu"]
        if net_data.get("description"):
            payload["description"] = net_data["description"]
        if net_data.get("mac_address"):
            payload["mac_address"] = self._normalize_mac(net_data["mac_address"])
        if net_data.get("speed"):
            # SuzieQ speed is in bps, NetBox expects kbps
            payload["speed"] = net_data["speed"] // 1000 if net_data["speed"] > 1000 else net_data["speed"]
        
        result = await self.netbox.execute(
            path="/api/dcim/interfaces/",
            method="POST",
            data=payload,
        )
        
        if result.error:
            console.print(f"    [red]创建失败: {result.error}[/red]")
            self.stats["errors"] += 1
        else:
            console.print(f"    [green]✓ 创建成功[/green]")
            self.stats["interfaces_created"] += 1

    async def _delete_interface(
        self,
        device: str,
        nb_data: dict[str, Any],
        report: ReconciliationReport,
    ) -> None:
        """从 NetBox 删除接口（网络上已不存在）"""
        ifname = nb_data["name"]
        nb_id = nb_data["id"]
        
        console.print(f"  [red]- 删除接口: {ifname}[/red] (网络上不存在)")
        
        report.missing_in_network += 1
        report.add_diff(DiffResult(
            entity_type=EntityType.INTERFACE,
            device=device,
            field="existence",
            network_value="missing",
            netbox_value=ifname,
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
            identifier=ifname,
            netbox_id=nb_id,
            netbox_endpoint="/api/dcim/interfaces/",
        ))
        
        if self.dry_run:
            console.print(f"    [dim](dry run - 不会真正删除)[/dim]")
            return
        
        # HITL 确认
        if not self.skip_hitl:
            confirm = Confirm.ask(f"    确认删除接口 {ifname}?", default=False)
            if not confirm:
                console.print(f"    [yellow]跳过删除[/yellow]")
                self.stats["skipped"] += 1
                return
        
        result = await self.netbox.execute(
            path=f"/api/dcim/interfaces/{nb_id}/",
            method="DELETE",
        )
        
        if result.error:
            console.print(f"    [red]删除失败: {result.error}[/red]")
            self.stats["errors"] += 1
        else:
            console.print(f"    [green]✓ 删除成功[/green]")
            self.stats["interfaces_deleted"] += 1

    async def _update_interface(
        self,
        device: str,
        ifname: str,
        net_data: dict[str, Any],
        nb_data: dict[str, Any],
        report: ReconciliationReport,
    ) -> None:
        """更新接口字段以匹配网络状态"""
        updates = {}
        diffs_found = []
        
        # 比较 enabled/adminState
        net_enabled = net_data.get("adminState", "up") == "up"
        nb_enabled = nb_data.get("enabled", True)
        if net_enabled != nb_enabled:
            updates["enabled"] = net_enabled
            diffs_found.append(f"enabled: {nb_enabled} → {net_enabled}")
        
        # 比较 MTU
        net_mtu = net_data.get("mtu")
        nb_mtu = nb_data.get("mtu")
        if net_mtu and net_mtu != nb_mtu:
            updates["mtu"] = net_mtu
            diffs_found.append(f"mtu: {nb_mtu} → {net_mtu}")
        
        # 比较 speed
        net_speed = net_data.get("speed")
        if net_speed:
            net_speed_kbps = net_speed // 1000 if net_speed > 1000 else net_speed
            nb_speed = nb_data.get("speed")
            if net_speed_kbps != nb_speed:
                updates["speed"] = net_speed_kbps
                diffs_found.append(f"speed: {nb_speed} → {net_speed_kbps}")
        
        # 比较 MAC address
        # NOTE: NetBox 4.x 使用 mac_addresses (复数) 关联表，而非直接存储
        # 跳过 MAC 地址比较，因为它需要创建单独的 MAC 地址对象
        # net_mac = net_data.get("macaddr")
        # if net_mac:
        #     net_mac_normalized = self._normalize_mac(net_mac)
        #     nb_mac = nb_data.get("mac_address")
        #     if net_mac_normalized and net_mac_normalized.lower() != (nb_mac or "").lower():
        #         updates["mac_address"] = net_mac_normalized
        #         diffs_found.append(f"mac: {nb_mac} → {net_mac_normalized}")
        
        # 比较 description
        net_desc = net_data.get("description", "")
        nb_desc = nb_data.get("description", "")
        if net_desc and net_desc != nb_desc:
            updates["description"] = net_desc
            diffs_found.append(f"description: '{nb_desc}' → '{net_desc}'")
        
        if not updates:
            report.add_match()
            return
        
        # 有差异，记录并更新
        console.print(f"  [yellow]~ 更新接口: {ifname}[/yellow]")
        for diff in diffs_found:
            console.print(f"    {diff}")
            report.add_diff(DiffResult(
                entity_type=EntityType.INTERFACE,
                device=device,
                field=f"{ifname}.{diff.split(':')[0]}",
                network_value=str(updates.get(diff.split(':')[0].strip(), "")),
                netbox_value=str(nb_data.get(diff.split(':')[0].strip(), "")),
                severity=DiffSeverity.INFO,
                source=DiffSource.SUZIEQ,
                identifier=ifname,
                netbox_id=nb_data["id"],
                netbox_endpoint="/api/dcim/interfaces/",
                auto_correctable=True,
            ))
        
        if self.dry_run:
            console.print(f"    [dim](dry run - 不会真正更新)[/dim]")
            return
        
        result = await self.netbox.execute(
            path=f"/api/dcim/interfaces/{nb_data['id']}/",
            method="PATCH",
            data=updates,
        )
        
        if result.error:
            console.print(f"    [red]更新失败: {result.error}[/red]")
            self.stats["errors"] += 1
        else:
            console.print(f"    [green]✓ 更新成功[/green]")
            self.stats["interfaces_updated"] += 1

    async def _sync_ip_addresses(self, device: str, report: ReconciliationReport) -> None:
        """同步 IP 地址"""
        console.print("\n[cyan]🌐 同步 IP 地址...[/cyan]")
        
        # 从 SuzieQ 获取 IP（在 interfaces 表的 ipAddressList 字段）
        sq_result = await suzieq_query.ainvoke({
            "table": "interfaces",
            "method": "get",
            "hostname": device,
        })
        
        # 获取设备 ID
        device_result = await self.netbox.execute(
            path="/api/dcim/devices/",
            method="GET",
            params={"name": device},
        )
        
        if device_result.error or not device_result.data:
            return
        
        device_id = device_result.data[0]["id"]
        
        # 获取 NetBox IP 地址
        nb_result = await self.netbox.execute(
            path="/api/ipam/ip-addresses/",
            method="GET",
            params={"device_id": device_id},
        )
        
        # 解析网络 IP
        network_ips = self._parse_suzieq_ips(sq_result, device)
        
        # 解析 NetBox IP
        netbox_ips = {}
        for ip in (nb_result.data or []):
            addr = ip.get("address", "")
            assigned = ip.get("assigned_object") or {}
            netbox_ips[addr] = {
                "id": ip["id"],
                "interface": assigned.get("name") if assigned else None,
                "status": ip.get("status", {}).get("value") if isinstance(ip.get("status"), dict) else ip.get("status"),
            }
        
        console.print(f"  网络 IP: {len(network_ips)} 个")
        console.print(f"  NetBox IP: {len(netbox_ips)} 个")
        
        # 对比
        all_ips = set(network_ips.keys()) | set(netbox_ips.keys())
        
        for ip in sorted(all_ips):
            net_data = network_ips.get(ip)
            nb_data = netbox_ips.get(ip)
            
            if net_data and not nb_data:
                await self._create_ip(device, device_id, ip, net_data, report)
            elif nb_data and not net_data:
                await self._delete_ip(device, ip, nb_data, report)
            # IP 字段很少需要更新，主要是存在性检查

    async def _create_ip(
        self,
        device: str,
        device_id: int,
        ip: str,
        net_data: dict[str, Any],
        report: ReconciliationReport,
    ) -> None:
        """在 NetBox 创建 IP 地址"""
        console.print(f"  [green]+ 创建 IP: {ip}[/green] (接口: {net_data.get('interface')})")
        
        report.missing_in_netbox += 1
        report.add_diff(DiffResult(
            entity_type=EntityType.IP_ADDRESS,
            device=device,
            field="existence",
            network_value="present",
            netbox_value="missing",
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
            identifier=ip,
            additional_context=net_data,
        ))
        
        if self.dry_run:
            console.print(f"    [dim](dry run)[/dim]")
            return
        
        # 查找接口 ID
        interface_id = None
        if net_data.get("interface"):
            intf_result = await self.netbox.execute(
                path="/api/dcim/interfaces/",
                method="GET",
                params={"device_id": device_id, "name": net_data["interface"]},
            )
            if not intf_result.error and intf_result.data:
                interface_id = intf_result.data[0]["id"]
        
        payload = {
            "address": ip,
            "status": "active",
        }
        
        if interface_id:
            payload["assigned_object_type"] = "dcim.interface"
            payload["assigned_object_id"] = interface_id
        
        result = await self.netbox.execute(
            path="/api/ipam/ip-addresses/",
            method="POST",
            data=payload,
        )
        
        if result.error:
            console.print(f"    [red]创建失败: {result.error}[/red]")
            self.stats["errors"] += 1
        else:
            console.print(f"    [green]✓ 创建成功[/green]")
            self.stats["ips_created"] += 1

    async def _delete_ip(
        self,
        device: str,
        ip: str,
        nb_data: dict[str, Any],
        report: ReconciliationReport,
    ) -> None:
        """从 NetBox 删除 IP（网络上不存在）"""
        console.print(f"  [red]- 删除 IP: {ip}[/red] (网络上不存在)")
        
        report.missing_in_network += 1
        report.add_diff(DiffResult(
            entity_type=EntityType.IP_ADDRESS,
            device=device,
            field="existence",
            network_value="missing",
            netbox_value=ip,
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
            identifier=ip,
            netbox_id=nb_data["id"],
            netbox_endpoint="/api/ipam/ip-addresses/",
        ))
        
        if self.dry_run:
            console.print(f"    [dim](dry run)[/dim]")
            return
        
        if not self.skip_hitl:
            confirm = Confirm.ask(f"    确认删除 IP {ip}?", default=False)
            if not confirm:
                self.stats["skipped"] += 1
                return
        
        result = await self.netbox.execute(
            path=f"/api/ipam/ip-addresses/{nb_data['id']}/",
            method="DELETE",
        )
        
        if result.error:
            console.print(f"    [red]删除失败: {result.error}[/red]")
            self.stats["errors"] += 1
        else:
            console.print(f"    [green]✓ 删除成功[/green]")
            self.stats["ips_deleted"] += 1

    async def _sync_device_info(self, device: str, report: ReconciliationReport) -> None:
        """同步设备信息（serial, version 等）"""
        console.print("\n[cyan]🖥️ 同步设备信息...[/cyan]")
        
        # SuzieQ device 表
        sq_result = await suzieq_query.ainvoke({
            "table": "device",
            "method": "get",
            "hostname": device,
        })
        
        # 检查是否有数据
        if isinstance(sq_result, dict):
            if sq_result.get("status") in ["NO_DATA_FOUND", "SCHEMA_NOT_FOUND"]:
                console.print("  [dim]SuzieQ 无设备表数据，跳过[/dim]")
                return
            data = sq_result.get("data", [])
            if not data:
                console.print("  [dim]SuzieQ 无设备数据，跳过[/dim]")
                return
        
        # 解析 SuzieQ 设备数据
        sq_device = None
        for row in sq_result.get("data", []):
            if row.get("hostname") == device:
                sq_device = row
                break
        
        if not sq_device:
            console.print("  [dim]未找到设备数据[/dim]")
            return
        
        # 获取 NetBox 设备
        nb_result = await self.netbox.execute(
            path="/api/dcim/devices/",
            method="GET",
            params={"name": device},
        )
        
        if nb_result.error or not nb_result.data:
            return
        
        nb_device = nb_result.data[0]
        updates = {}
        diffs_found = []
        
        # 比较 serial
        net_serial = sq_device.get("serialNumber")
        nb_serial = nb_device.get("serial")
        if net_serial and net_serial != nb_serial:
            updates["serial"] = net_serial
            diffs_found.append(f"serial: {nb_serial} → {net_serial}")
        
        # 比较 version (存储在 custom_fields 或 comments)
        net_version = sq_device.get("version")
        if net_version:
            # 更新到 comments 或 custom_fields
            current_comments = nb_device.get("comments", "")
            version_tag = f"Software Version: {net_version}"
            if version_tag not in current_comments:
                updates["comments"] = f"{current_comments}\n{version_tag}".strip()
                diffs_found.append(f"version: → {net_version}")
        
        if not updates:
            console.print("  [dim]设备信息已同步[/dim]")
            report.add_match()
            return
        
        console.print(f"  [yellow]~ 更新设备信息[/yellow]")
        for diff in diffs_found:
            console.print(f"    {diff}")
        
        if self.dry_run:
            console.print(f"    [dim](dry run)[/dim]")
            return
        
        result = await self.netbox.execute(
            path=f"/api/dcim/devices/{nb_device['id']}/",
            method="PATCH",
            data=updates,
        )
        
        if result.error:
            console.print(f"    [red]更新失败: {result.error}[/red]")
            self.stats["errors"] += 1
        else:
            console.print(f"    [green]✓ 更新成功[/green]")
            self.stats["devices_updated"] += 1

    # ========== Helper Methods ==========

    def _parse_suzieq_interfaces(
        self, result: dict[str, Any], device: str
    ) -> dict[str, dict[str, Any]]:
        """解析 SuzieQ 接口数据"""
        interfaces = {}
        
        if not isinstance(result, dict):
            return interfaces
        
        for row in result.get("data", []):
            if row.get("hostname") == device:
                ifname = row.get("ifname", "")
                if ifname:
                    interfaces[ifname] = {
                        "state": row.get("state"),
                        "adminState": row.get("adminState"),
                        "mtu": row.get("mtu"),
                        "speed": row.get("speed"),
                        "type": row.get("type"),
                        "description": row.get("description", ""),
                        "macaddr": row.get("macaddr"),
                        "ipAddressList": row.get("ipAddressList", []),
                    }
        
        return interfaces

    def _parse_suzieq_ips(
        self, result: dict[str, Any], device: str
    ) -> dict[str, dict[str, Any]]:
        """从 SuzieQ interfaces 表提取 IP 地址"""
        ips = {}
        
        if not isinstance(result, dict):
            return ips
        
        for row in result.get("data", []):
            if row.get("hostname") == device:
                ifname = row.get("ifname", "")
                ip_list = row.get("ipAddressList", [])
                
                if isinstance(ip_list, str):
                    ip_list = [ip_list]
                
                for ip in ip_list:
                    if ip:
                        ips[ip] = {
                            "interface": ifname,
                            "vrf": row.get("vrf", "default"),
                        }
        
        return ips

    def _map_interface_type(self, ifname: str, sq_type: str | None) -> str:
        """映射接口类型到 NetBox 类型"""
        # NetBox 接口类型 slug
        ifname_lower = ifname.lower()
        
        if "loopback" in ifname_lower or ifname_lower.startswith("lo"):
            return "virtual"
        if "vlan" in ifname_lower:
            return "virtual"
        if "tunnel" in ifname_lower or "gre" in ifname_lower:
            return "virtual"
        if "gigabit" in ifname_lower or "ge-" in ifname_lower or ifname_lower.startswith("gi"):
            return "1000base-t"
        if "tengigabit" in ifname_lower or "te-" in ifname_lower:
            return "10gbase-t"
        if "fastethernet" in ifname_lower or ifname_lower.startswith("fa"):
            return "100base-tx"
        if "ethernet" in ifname_lower or ifname_lower.startswith("eth"):
            return "1000base-t"
        
        return "other"

    def _normalize_mac(self, mac: str | None) -> str | None:
        """规范化 MAC 地址格式为 NetBox 格式 (AA:BB:CC:DD:EE:FF)"""
        if not mac:
            return None
        
        # 移除所有分隔符
        mac_clean = mac.replace(":", "").replace("-", "").replace(".", "").upper()
        
        if len(mac_clean) != 12:
            return None
        
        # 格式化为 AA:BB:CC:DD:EE:FF
        return ":".join(mac_clean[i:i+2] for i in range(0, 12, 2))

    def print_summary(self) -> None:
        """打印同步摘要"""
        table = Table(title="同步摘要", show_header=True)
        table.add_column("操作", style="cyan")
        table.add_column("数量", justify="right")
        
        table.add_row("接口创建", str(self.stats["interfaces_created"]))
        table.add_row("接口删除", str(self.stats["interfaces_deleted"]))
        table.add_row("接口更新", str(self.stats["interfaces_updated"]))
        table.add_row("IP 创建", str(self.stats["ips_created"]))
        table.add_row("IP 删除", str(self.stats["ips_deleted"]))
        table.add_row("设备更新", str(self.stats["devices_updated"]))
        table.add_row("[yellow]跳过[/yellow]", str(self.stats["skipped"]))
        table.add_row("[red]错误[/red]", str(self.stats["errors"]))
        
        console.print("\n")
        console.print(table)


async def get_all_devices() -> list[str]:
    """获取 NetBox 中所有设备"""
    netbox = NetBoxAPITool()
    result = await netbox.execute(
        path="/api/dcim/devices/",
        method="GET",
    )
    
    if result.error:
        console.print(f"[red]获取设备列表失败: {result.error}[/red]")
        return []
    
    return [d["name"] for d in (result.data or [])]


async def main() -> None:
    parser = argparse.ArgumentParser(description="强制同步网络状态到 NetBox")
    parser.add_argument("--device", "-d", help="指定设备名称")
    parser.add_argument("--all", "-a", action="store_true", help="同步所有设备")
    parser.add_argument("--apply", action="store_true", help="真正执行变更 (默认 dry run)")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过 HITL 确认")
    
    args = parser.parse_args()
    
    if not args.device and not args.all:
        parser.print_help()
        console.print("\n[yellow]请指定 --device 或 --all[/yellow]")
        return
    
    # 显示模式
    mode = "[red]APPLY MODE[/red]" if args.apply else "[green]DRY RUN MODE[/green]"
    console.print(Panel(
        f"🔄 Force Sync - 强制同步网络状态到 NetBox\n\n"
        f"模式: {mode}\n"
        f"HITL: {'跳过' if args.yes else '启用'}",
        title="OLAV Force Sync",
    ))
    
    # 获取设备列表
    if args.all:
        devices = await get_all_devices()
        console.print(f"\n找到 {len(devices)} 个设备: {', '.join(devices)}")
    else:
        devices = [args.device]
    
    # 执行同步
    engine = ForceSyncEngine(
        dry_run=not args.apply,
        skip_hitl=args.yes,
    )
    
    for device in devices:
        try:
            await engine.sync_device(device)
        except Exception as e:
            console.print(f"[red]同步 {device} 失败: {e}[/red]")
            engine.stats["errors"] += 1
    
    # 打印摘要
    engine.print_summary()
    
    if not args.apply:
        console.print("\n[yellow]💡 这是 dry run 模式，添加 --apply 以真正执行变更[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
