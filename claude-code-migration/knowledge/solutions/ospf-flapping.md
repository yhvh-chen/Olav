# Case: OSPF Neighbor Flapping Causing Route Instability

> **Created**: 2026-01-07
> **Fault Type**: Routing Protocol Fault
> **Impact Scope**: Network area routing reachability issue

## Problem Description

Network monitoring detected OSPF neighbors repeatedly establishing and breaking, causing routing table changes, some services intermittent.
- **Symptoms**: OSPF neighbor state repeatedly switching between Full <-> Init
- **Impact**: Route table flapping, traffic paths frequently changing
- **Duration**: 4 hours

## Troubleshooting Process

### 1. Initial Diagnosis (Macro Analysis)
```bash
# Check OSPF neighbor status
show ip ospf neighbor

# Finding:
# Neighbor ID: 10.2.1.1
# State: FULL (30 seconds ago) -> INIT (current) -> FULL (repeating)
# Dead time: unstable

# Check OSPF interface status
show ip ospf interface brief
# Finding: GigabitEthernet0/1 state frequently changing
```

**Conclusion**: OSPF neighbor relationship unstable, requires further investigation

### 2. Check Network Layer Connectivity (Micro Analysis)
```bash
# Test layer 3 connectivity
ping 10.2.1.1 -c 100
# Result: 2% packet loss, occasional timeouts

# Check interface status
show interfaces GigabitEthernet0/1
# Finding: Interface status stable, up/up

# Check MTU settings
show interfaces GigabitEthernet0/1 | include MTU
# Finding: MTU 1500 (normal)
```

**Initial Assessment**: Physical layer normal, issue may be in OSPF config or layer 3

### 3. Deep OSPF Configuration Check
```bash
# Check OSPF configuration
show running-config | section router ospf

# Finding problems:
# interface GigabitEthernet0/1
#  ip ospf hello-interval 5
#  ip ospf dead-interval 20

# Check remote side configuration (by logging into remote device)
# interface remote side
#  ip ospf hello-interval 10  # Mismatch!
#  ip ospf dead-interval 40   # Mismatch!
```

**Root Cause Located**: OSPF Hello/Dead timer mismatch

### 4. Verify Root Cause
```bash
# Check OSPF logs
show logging | include OSPF
# Finding:
# %OSPF-5-ADJCHG: Process 1, Nbr 10.2.1.1 on GigabitEthernet0/1 from FULL to INIT
# (repeating)

# Real-time monitor OSPF events
debug ip ospf adj
# Observation: Hello timer mismatch prevents neighbors from maintaining FULL state
```

## Root Cause

**OSPF Hello/Dead Interval Configuration Mismatch**

- **Local**: Hello 5s, Dead 20s
- **Remote**: Hello 10s, Dead 40s
- **OSPF Requirement**: All routers on same segment must have identical OSPF timers

**Impact**: Neighbors cannot maintain stable relationship, repeatedly cycle Init->Full->Init

## Solution

### Immediate Fix (Recommended during maintenance window)
```bash
# Option 1: Standardize to standard values (recommended)
interface GigabitEthernet0/1
 ip ospf hello-interval 10
 ip ospf dead-interval 40

# Option 2: Standardize to fast convergence values (for special cases)
interface GigabitEthernet0/1
 ip ospf hello-interval 5
 ip ospf dead-interval 20
# 同时在对端也做相同配置
```

### 验证配置
```bash
# 1. 检查本端配置
show ip ospf interface GigabitEthernet0/1 | include Timer
# 确认: Hello 10, Dead 40, Wait 40

# 2. 检查对端配置 (协同检查)
# 通过SSH登录对端,执行相同命令

# 3. 重置OSPF进程 (可选,加速收敛)
clear ip ospf process

# 4. 验证邻居状态
show ip ospf neighbor
# 期望: State: FULL, 保持稳定
```

### 验证结果
```bash
# 持续监控10分钟
watch -n 5 "show ip ospf neighbor | include 10.2.1.1"
# 观察: State 应持续保持 FULL

# 检查路由表稳定性
show ip route ospf
# 期望: 路由条目不再频繁变化
```

## 验证结果

✅ **配置统一后**:
- OSPF邻居状态: 稳定在 FULL
- 路由表: 稳定,不再震荡
- 业务: 完全恢复
- 监控: 24小时内无OSPF告警

## 关键命令

| 命令 | 用途 |
|------|------|
| `show ip ospf neighbor` | OSPF邻居状态 |
| `show ip ospf interface brief` | OSPF接口状态 |
| `show ip ospf interface <if>` | OSPF接口详细参数 |
| `show running-config \| section router ospf` | OSPF配置 |
| `debug ip ospf adj` | 实时OSPF事件调试 |
| `clear ip ospf process` | 重置OSPF进程 |

## 经验总结

### OSPF邻居震荡排查流程
1. **发现**: 邻居状态在 Full <-> Init <-> Loading 之间切换
2. **检查连通性**: ping 测试,确保三层可达
3. **检查接口**: `show interfaces` 确保接口up/up
4. **检查配置**: Hello/Dead interval, Area ID, Authentication
5. **检查网络**: MTU匹配,ACL阻断,网络可达性
6. **检查资源**: CPU,内存,路由表容量

### OSPF常见故障原因
| 故障类型 | 症状 | 检查方法 |
|---------|------|---------|
| Timer不匹配 | 邻居无法建立或反复INIT | `show ip ospf interface` |
| Area ID不匹配 | 邻居停留在2-Way | `show ip ospf` |
| MTU不匹配 | 邻居停留在 ExStart/Exchange | `show interfaces` |
| 认证失败 | 邻居无法建立 | `debug ip ospf adj` |
| 网络不可达 | 邻居Down | `ping` 测试 |
| Router ID冲突 | 邻居震荡 | `show ip ospf` |

### 预防措施
- **标准化配置**: 统一OSPF timer模板
  ```
  interface范围
   ip ospf hello-interval 10
   ip ospf dead-interval 40
  ```
- **配置审计**: 定期检查OSPF配置一致性
- **监控告警**: 配置OSPF邻居状态监控
  ```
  if (OSPF neighbor != FULL for > 60s):
      触发告警
  ```
- **变更管理**: OSPF配置变更需审批和测试

## 标签
#OSPF #路由协议 #邻居震荡 #网络层 #路由故障 #配置一致性

## 相关案例
- [BGP邻居建立失败](./bgp-establishment.md) - BGP协议故障
- [路由环路](./routing-loop.md) - 路由配置错误
