# 案例: BGP 邻居建立失败 - ASN 配置错误

> **创建时间**: 2026-01-07
> **故障类型**: 路由协议故障
> **影响范围**: 外部网络连接中断

## 问题描述

新上线站点与运营商BGP连接无法建立,导致外部路由无法学习,该站点与外部网络通信中断。
- **症状**: BGP邻居状态持续停留在 Idle/Connect
- **影响**: 无法与运营商交换路由,外部业务中断
- **持续时间**: 新站点上线后持续存在

## 排查过程

### 1. 初步诊断 (宏观分析)
```bash
# 检查BGP邻居状态
show ip bgp summary

# 发现:
# Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
# 203.0.113.2     4   65001      0       3        0    0    0 never    Idle
#
# 状态: Idle (从未达到 Established)

# 检查BGP配置
show running-config | section router bgp

# 配置:
# router bgp 65002
#  neighbor 203.0.113.2 remote-as 65001
#  neighbor 203.0.113.2 description ISP-Primary
```

**初步分析**: BGP配置存在,但邻居无法建立

### 2. 检查网络层连通性
```bash
# 测试三层连通性
ping 203.0.113.2 -c 10
# 结果: 100% 可达,延迟正常

# 测试TCP端口179 (BGP端口)
telnet 203.0.113.2 179
# 结果: Trying 203.0.113.2... Connected
# 端口可达,BGP未建立说明配置问题
```

**判断**: 网络层正常,问题在BGP配置

### 3. 检查BGP详细配置
```bash
# 检查本端BGP配置
show ip bgp neighbors 203.0.113.2

# 关键信息:
# BGP state = Idle
# BGP version = 4, remote router ID 0.0.0.0
#  Last read 00:00:00, Last write 00:00:00
#  Hold time is 180, keepalive interval is 60 seconds

# 检查BGP日志
show logging | include BGP
# 发现:
# %BGP-3-NOTIFICATION: received from neighbor 203.0.113.2
#  (Bad Peer AS)
```

**根因线索**: "Bad Peer AS" - 对端拒绝了我的AS号

### 4. 验证ASN配置
```bash
# 与运营商确认正确的ASN
# 运营商告知: 客户端应使用 ASN 65003,不是 65002

# 检查合同文档
# 发现: 运营商分配的ASN确实是 65003

# 根因确认: 本端ASN配置错误!
```

## 根因

**本端BGP ASN配置错误**

- **错误配置**: `router bgp 65002`
- **正确配置**: `router bgp 65003`
- **原因**: 运营商分配的ASN是 65003,但配置时误用了旧的ASN 65002

**影响**: 对端运营商收到错误ASN的BGP OPEN消息,拒绝建立连接,返回"Bad Peer AS"错误

## 解决方案

### 立即修复
```bash
# 1. 进入配置模式
configure terminal

# 2. 删除错误的BGP配置
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
