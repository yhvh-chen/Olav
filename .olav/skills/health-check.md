# Health Check (系统健康检查)

## 适用场景
- 定期设备健康检查
- 设备上线前验证
- 资源使用监控
- 系统状态巡检

## 识别标志
用户问题包含: "健康检查"、"系统状态"、"巡检"、"资源使用"、"CPU/内存"

## 执行策略
1. 使用 `write_todos` 规划检查项
2. 使用 `parse_inspection_scope()` 确定检查范围
3. 使用 `nornir_bulk_execute()` 批量执行检查命令
4. 分析结果，识别异常
5. 使用 `generate_report()` 生成健康检查报告

## 检查项

### 系统基础
- [ ] show version (版本、运行时间)
- [ ] show processes cpu history (CPU 趋势)
- [ ] show memory statistics (内存使用)
- [ ] show environment (温度、电源、风扇)

### 接口状态
- [ ] show interfaces status (端口状态概览)
- [ ] show interfaces counters (接口计数器)
- [ ] show ip interface brief (IP 接口状态)

### 路由状态
- [ ] show ip route summary (路由汇总)
- [ ] show ip ospf neighbor (OSPF 邻居)
- [ ] show ip bgp summary (BGP 邻居)

## 报告格式
使用 `generate_report(template="health-check")` 生成报告，包含：
- 设备列表
- 每项检查的结果
- 异常项高亮
- 资源使用趋势
- 建议措施

## 示例

### 执行健康检查
```
用户: "对所有核心交换机进行健康检查"

Agent 步骤:
1. parse_inspection_scope("all core routers")
   → 返回: {"devices": ["all"], "filters": {"role": "core"}}

2. nornir_bulk_execute(
       devices="all",
       commands=[
           "show version",
           "show processes cpu history",
           "show memory statistics",
           "show interfaces status"
       ],
       max_workers=10
   )

3. 分析结果:
   - 检查 CPU 使用率是否 >80%
   - 检查内存使用率是否 >85%
   - 检查接口是否有 error
   - 检查运行时间是否异常短

4. generate_report(
       template="health-check",
       results=results,
       output_path=".olav/reports/health-check-20250108.html"
   )
```

### 预期输出
```
✅ 健康检查完成

检查范围: 5 台核心交换机
检查时间: 2025-01-08 14:30

检查结果:
  CS-DC1: ✅ 正常 (CPU 15%, 内存 45%, 运行 45 天)
  CS-DC2: ✅ 正常 (CPU 12%, 内存 42%, 运行 45 天)
  CS-DC3: ⚠️  警告 (CPU 82%, 内存 78%, 运行 30 天)
  CS-DC4: ✅ 正常 (CPU 10%, 内存 40%, 运行 60 天)
  CS-DC5: ❌ 异常 (内存 90%, 接口 Gi0/1 有 CRC 错误)

报告已生成: .olav/reports/health-check-20250108.html

建议措施:
  - CS-DC3: CPU 使用率偏高，检查是否有进程异常
  - CS-DC5: 内存使用率过高，检查 Gi0/1 接口 CRC 错误原因
```
