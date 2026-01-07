# 案例: CRC 错误导致网络抖动

> **创建时间**: 2026-01-07
> **故障类型**: 物理层故障
> **影响范围**: 单链路性能下降

## 问题描述

用户反映某条专线网络时断时续,ping 测试丢包严重,业务访问不稳定。
- **症状**: 间歇性丢包,带宽利用率低
- **影响**: 关键业务无法正常使用
- **持续时间**: 2天

## 排查过程

### 1. 初步诊断 (宏观分析)
```bash
# 检查端到端路径
ping 10.2.1.1 -c 100
# 结果: 丢包率 15%, 延迟抖动大

# traceroute 定位问题节点
traceroute 10.2.1.1
# 结果: 第2跳（出口路由器）后开始丢包
```

**结论**: 问题定位在出口路由器到运营商之间

### 2. 接口检查 (微观分析 - 物理层)
```bash
# 检查接口状态
show interfaces GigabitEthernet0/0/1

# 关键发现:
# - Interface is up, line protocol is up
# - CRC errors: 12,345 (持续增长中)
# - Input errors: 12,350
# - Runts: 0, Giants: 0

# 检查光模块信息
show interfaces transceiver detail Gi0/0/1

# 关键发现:
# - RX power: -18.5 dBm (偏低,正常范围 -3 to -15 dBm)
# - TX power: -2.1 dBm (正常)
# - Temperature: 42°C (正常)
```

**根因定位**: 接收光功率过低,导致CRC错误增长

### 3. 进一步验证
```bash
# 检查错误增长趋势
show interfaces counters Gi0/0/1 | include CRC
# 30秒后再次检查
show interfaces counters Gi0/0/1 | include CRC
# CRC增长 +10 (持续增长)

# 检查光模块型号
show inventory
# 发现: 光模块使用3年,接近寿命极限
```

## 根因

**光模块老化,接收灵敏度下降,导致CRC错误增长**

- **物理原因**: 光模块激光器老化,发射功率稳定但接收灵敏度下降
- **环境因素**: 可能存在光链路污损或连接器氧化
- **影响链路**: GigabitEthernet0/0/1 (出口专线)

## 解决方案

### 立即措施
```bash
# 1. 临时: 降低接口速率至1G (如果当前是10G)
interface GigabitEthernet0/0/1
 speed 1000
 negotiation auto

# 2. 或者: 启用前向纠错 (如果光模块支持)
interface GigabitEthernet0/0/1
 fec mode rs
```

### 永久修复
1. **更换光模块** (优先级: 高)
   - 型号: SFP-10G-LR (匹配链路距离)
   - 品牌: 原厂或认证第三方
   - 预期: 恢复正常接收功率 (-3 to -15 dBm)

2. **检查光纤链路** (同步进行)
   - 清洁光纤连接器
   - 检查光衰是否在正常范围
   - 测试光纤完整性

3. **监控验证** (更换后)
   ```bash
   # 持续监控24小时
   show interfaces counters Gi0/0/1 | include CRC
   # CRC错误应不再增长

   # 验证接收功率
   show interfaces transceiver detail Gi0/0/1
   # RX power应恢复至 -3 to -15 dBm

   # 业务测试
   ping 10.2.1.1 -c 1000
   # 丢包率应 < 0.1%
   ```

## 验证结果

✅ **更换光模块后24小时监控**:
- CRC错误: 0增长
- RX power: -7.2 dBm (正常)
- 丢包率: 0%
- 带宽利用率: 恢复正常

## 关键命令

| 命令 | 用途 |
|------|------|
| `show interfaces status` | 接口状态概览 |
| `show interfaces counters errors` | 错误计数详情 |
| `show interfaces transceiver detail` | 光模块详细信息 |
| `show inventory` | 硬件清单 |
| `ping -c 100` | 丢包率测试 |

## 经验总结

### CRC错误排查流程
1. **发现**: 接口错误计数异常 (CRC errors > 0且持续增长)
2. **定位**: `show interfaces counters errors` 确认具体接口
3. **检查**: `show interfaces transceiver detail` 查看光功率
4. **判断**:
   - RX power < -20 dBm: 光模块/光纤断裂
   - RX power -15 to -20 dBm: 光功率不足,可能老化
   - RX power -3 to -15 dBm: 正常
5. **修复**: 更换光模块,清洁光纤,检查链路

### 预防措施
- 定期检查接口错误计数 (每周)
- 监控光功率趋势 (每月)
- 光模块寿命管理 (3-5年更换计划)
- 配置CRC告警阈值
  ```
  # 监控脚本示例
  if (CRC > 100 或 RX < -18 dBm):
      触发告警
  ```

## 标签
#物理层 #CRC错误 #光模块 #接口故障 #专线故障 #丢包

## 相关案例
- [MAC地址漂移](./mac-flapping.md) - 二层环路问题
- [BGP邻居震荡](./bgp-flapping.md) - 路由协议故障
