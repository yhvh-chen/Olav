# Interface Errors (接口错误分析)

## 适用场景
- 接口错误率异常
- CRC 错误诊断
- 丢包问题排查
- 物理层故障分析

## 识别标志
用户问题包含: "接口错误"、"CRC"、"丢包"、"error"、"包丢失"、"物理层"

## 执行策略
1. 使用 `parse_inspection_scope()` 确定检查范围
2. 使用 `nornir_bulk_execute()` 批量执行接口检查命令
3. 分析错误计数器、CRC、丢包
4. 定位问题接口和原因
5. 使用 `generate_report()` 生成接口错误报告

## 检查项

### 接口状态
- [ ] show interfaces status (接口状态)
- [ ] show interfaces counters errors (错误计数器)
- [ ] show interfaces counters (详细计数)

### 物理层
- [ ] show interfaces transceiver detail (光模块详情)
- [ ] show controllers <interface> (控制器信息)
- [ ] show logging | include interface (接口相关日志)

### 流量统计
- [ ] show interfaces <interface> (接口详情)
- [ ] show traffic interface <interface> (流量统计)

## 报告格式
使用 `generate_report(template="interface-errors")` 生成报告，包含：
- 接口列表及错误统计
- CRC 错误接口
- 丢包率高的接口
- 光模块状态异常
- 根因分析
- 建议措施

## 异常检测

### 关键指标
- CRC 错误 > 100 → 物理层问题
- Input errors > 1000 → 检查链路质量
- Output errors > 1000 → 检查本地配置
- 丢包率 > 1% → 网络拥塞或错误
- 接口 flapping (频繁 up/down) → 检查物理连接

### 常见原因
- CRC 错误: 光模块老化、光纤脏污、距离过长
- Input errors: 对端设备问题、链路质量差
- Output errors: 本地配置错误、资源不足
- Flapping: 线缆松动、配置冲突、STP 问题

## 示例

### 执行接口错误分析
```
用户: "分析所有核心交换机的接口错误"

Agent 步骤:
1. parse_inspection_scope("all 核心交换机")

2. nornir_bulk_execute(
       devices=["CS-DC1", "CS-DC2", "CS-DC3"],
       commands=[
           "show interfaces status",
           "show interfaces counters errors",
           "show interfaces transceiver detail"
       ],
       max_workers=5
   )

3. 分析结果:
   - 提取所有接口的 CRC、input/output errors
   - 识别错误率高的接口
   - 检查光模块状态
   - 关联接口状态

4. generate_report(template="interface-errors", results=results)
```

### 预期输出
```
✅ 接口错误分析完成

分析范围: 3 台核心交换机
分析时间: 2025-01-08 16:00

接口错误汇总:
  CS-DC1:
    ✅ Gi0/1-48: 正常 (无错误)
    ✅ Te0/1-4: 正常 (无错误)

  CS-DC2:
    ✅ Gi0/1-48: 正常 (无错误)
    ⚠️  Te0/2: CRC 错误 1,523 个 ← 异常
       Rx Power: -18.5 dBm (偏低)
       建议: 更换光模块或检查光纤连接

  CS-DC3:
    ⚠️  Gi0/24: Input errors 2,340 个, CRC 错误 856 个
       Status: up, but errors increasing
       建议: 检查对端设备和物理链路

异常接口列表:
  1. CS-DC2 Te0/2 - CRC 错误
     错误类型: CRC
     错误计数: 1,523
     可能原因: 光模块发射功率过低 (-18.5 dBm)
     建议: 更换光模块

  2. CS-DC3 Gi0/24 - Input/CRC 错误
     错误类型: Input errors, CRC
     错误计数: 2,340 / 856
     可能原因: 链路质量差、对端设备问题
     建议: 检查物理连接、检查对端设备接口

报告已生成: .olav/reports/interface-errors-20250108.html
```
