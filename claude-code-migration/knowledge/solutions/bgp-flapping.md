# Case: BGP Neighbor Establishment Failure - ASN Configuration Error

> **Created**: 2026-01-07
> **Fault Type**: Routing Protocol Fault
> **Impact Scope**: External network connectivity interrupted

## Problem Description

New site's BGP connection with ISP failed to establish, preventing external route learning, resulting in communication interruption between the site and external network.
- **Symptoms**: BGP neighbor state remains in Idle/Connect
- **Impact**: Cannot exchange routes with ISP, external business interrupted
- **Duration**: Continuous since site deployment

## Troubleshooting Process

### 1. Initial Diagnosis (Macro Analysis)
```bash
# Check BGP neighbor status
show ip bgp summary

# Finding:
# Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
# 203.0.113.2     4   65001      0       3        0    0    0 never    Idle
#
# Status: Idle (never reached Established)

# Check BGP configuration
show running-config | section router bgp

# Configuration:
# router bgp 65002
#  neighbor 203.0.113.2 remote-as 65001
#  neighbor 203.0.113.2 description ISP-Primary
```

**Initial Analysis**: BGP configured but neighbor cannot establish

### 2. Check Network Layer Connectivity
```bash
# Test layer 3 connectivity
ping 203.0.113.2 -c 10
# Result: 100% reachable, normal latency

# Test TCP port 179 (BGP port)
telnet 203.0.113.2 179
# Result: Trying 203.0.113.2... Connected
# Port reachable, BGP not established suggests config issue
```

**Assessment**: Network layer normal, problem is in BGP configuration

### 3. Check BGP Detailed Configuration
```bash
# Check local BGP configuration
show ip bgp neighbors 203.0.113.2

# Key Info:
# BGP state = Idle
# BGP version = 4, remote router ID 0.0.0.0
#  Last read 00:00:00, Last write 00:00:00
#  Hold time is 180, keepalive interval is 60 seconds

# Check BGP logs
show logging | include BGP
# Finding:
# %BGP-3-NOTIFICATION: received from neighbor 203.0.113.2
#  (Bad Peer AS)
```

**Root Cause Clue**: "Bad Peer AS" - remote rejected my AS number

### 4. Verify ASN Configuration
```bash
# Confirm correct ASN with ISP
# ISP informed: Customer should use ASN 65003, not 65002

# Check contract documents
# Finding: ISP indeed assigned ASN 65003

# Root cause confirmed: Local BGP ASN misconfigured!
```

## Root Cause

**Local BGP ASN Configuration Error**

- **Incorrect Configuration**: `router bgp 65002`
- **Correct Configuration**: `router bgp 65003`
- **Reason**: ISP assigned ASN 65003, but configured with old ASN 65002

**Impact**: ISP receives wrong ASN in BGP OPEN message, refuses connection, returns "Bad Peer AS" error

## Solution

### Immediate Fix
```bash
# 1. Enter configuration mode
configure terminal

# 2. Delete incorrect BGP configuration
no router bgp 65002

# 3. 重新配置正确的BGP
router bgp 65003
 bgp router-id 203.0.113.1
 neighbor 203.0.113.2 remote-as 65001
 neighbor 203.0.113.2 description ISP-Primary
 neighbor 203.0.113.2 password 7 <encrypted-password>
 network 203.0.113.0 mask 255.255.255.252

# 4. 保存配置
end
write memory
```

### 验证配置
```bash
# 1. 检查BGP状态
show ip bgp summary
# 期望: State: Established

# 2. 检查路由学习
show ip bgp
# 期望: 收到运营商路由

# 3. 检查路由表
show ip route bgp
# 期望: BGP路由已安装到路由表

# 4. 验证连通性
ping 8.8.8.8 source 203.0.113.1
# 期望: 外部可达
```

### 验证结果
```bash
# 持续监控10分钟
watch -n 10 "show ip bgp summary | include 203.0.113.2"
# 观察: State/PfxRcd 应显示 Established 和收到的路由数量

# 检查BGP路由表稳定性
show ip bgp regex _65001_
# 期望: 收到运营商路由前缀
```

## 验证结果

✅ **ASN修正后**:
- BGP邻居状态: Established
- 收到路由前缀: 245条 (符合预期)
- 外部连通性: 完全恢复
- 24小时监控: 无BGP断连

## 关键命令

| 命令 | 用途 |
|------|------|
| `show ip bgp summary` | BGP邻居状态概览 |
| `show ip bgp neighbors <ip>` | BGP邻居详细信息 |
| `show running-config \| section router bgp` | BGP配置 |
| `show ip bgp` | BGP路由表 |
| `show logging \| include BGP` | BGP相关日志 |
| `telnet <ip> 179` | 测试BGP端口可达性 |
| `clear ip bgp <ip>` | 重置BGP邻居 |

## 经验总结

### BGP邻居建立失败排查流程
1. **检查状态**: `show ip bgp summary` - 确认邻居状态
2. **验证连通性**:
   - ping 测试三层可达性
   - telnet <ip> 179 测试TCP 179端口
3. **检查配置**:
   - 本端ASN: `router bgp <本地ASN>`
   - 对端ASN: `neighbor <ip> remote-as <对端ASN>`
   - 路由宣告: `network` 或 `redistribute`
4. **检查日志**: `show logging | include BGP` - 查看错误信息
5. **验证参数**:
   - ASN配置
   - 认证密码 (如使用MD5)
   - eBGP多跳 (如需要)
   - 路由策略

### BGP常见故障原因
| 故障类型 | 症状 | 检查方法 |
|---------|------|---------|
| ASN配置错误 | Idle, "Bad Peer AS" | 检查router bgp配置 |
| 网络不可达 | Idle, 无法连接 | ping/telnet测试 |
| 端口阻塞 | Connect, 无法建立 | ACL检查,防火墙规则 |
| ASN不匹配 | Active | 检查neighbor remote-as |
| 认证失败 | Idle | 检查password配置 |
| 路由策略 | Established but 0 routes | 检查route-map, prefix-list |
| eBGP多跳 | Idle (多跳场景) | 配置ebgp-multihop |

### 预防措施
- **配置标准化**: 使用BGP配置模板
  ```
  router bgp <分配的ASN>
   bgp router-id <Loopback地址>
   bgp log-neighbor-changes
   neighbor <对端IP> remote-as <对端ASN>
   neighbor <对端IP> description <清晰描述>
   neighbor <对端IP> password <加密密码>
   neighbor <对端IP> ebgp-multihop <跳数> (如需要)
  ```
- **配置审计**: 上线前与运营商/对端确认ASN参数
- **文档管理**: 维护BGP连接参数清单
  ```
  站点 | 本地ASN | 对端ASN | 对端IP | 用途 | 密钥
  ----|--------|--------|-------|------|------
  A   | 65003  | 65001  | x.x.x.x | ISP主| xxx
  ```
- **监控告警**:
  ```
  if (BGP state != Established for > 120s):
      触发严重告警
  if (BGP routes learned == 0):
      触发警告告警
  ```

## 标签
#BGP #路由协议 #ASN配置 #外部连接 #运营商对接 #BGP建立

## 相关案例
- [OSPF邻居震荡](./ospf-flapping.md) - 内部路由协议故障
- [路由泄露](./route-leak.md) - BGP路由策略错误
