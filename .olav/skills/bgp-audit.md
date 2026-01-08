# BGP Audit (BGP 审计)

## 适用场景
- BGP 邻居状态检查
- 路由表审计
- AS 路径验证
- BGP 策略合规性检查

## 识别标志
用户问题包含: "BGP"、"路由协议"、"AS号"、"BGP邻居"、"路由策略"

## 执行策略
1. 使用 `parse_inspection_scope()` 确定 BGP 设备范围
2. 使用 `nornir_bulk_execute()` 批量执行 BGP 检查命令
3. 分析 BGP 邻居状态、路由表
4. 识别异常邻居、路由振荡
5. 使用 `generate_report()` 生成 BGP 审计报告

## 检查项

### BGP 邻居状态
- [ ] show ip bgp summary (邻居汇总)
- [ ] show ip bgp neighbors (邻居详细信息)
- [ ] show ip bgp neighbors | include Idle (检查空闲邻居)

### 路由表
- [ ] show ip route bgp (BGP 路由)
- [ ] show ip bgp (BGP 表)
- [ ] show ip bgp regexp _AS_NUMBER_ (特定 AS 路由)

### 路径验证
- [ ] show ip bgp neighbors <peer> advertised-routes (宣告路由)
- [ ] show ip bgp neighbors <peer> received-routes (接收路由)
- [ ] traceroute <target> (路径验证)

## 报告格式
使用 `generate_report(template="bgp-audit")` 生成报告，包含：
- BGP 邻居列表及状态
- 路由统计
- 异常邻居/路由
- AS 路径信息
- 建议措施

## 异常检测

### 关键问题
- 邻居状态为 Idle 或 Active
- 路由表条目异常增长
- 收到来自错误 AS 的路由
- 路由振荡 (flapping)

### 告警阈值
- 邻居建立时间 < 1 小时 → 潜在不稳定
- BGP 表大小 > 10000 条 → 检查路由泄漏
- 路由接收速率异常 → 检查路由更新

## 示例

### 执行 BGP 审计
```
用户: "审计所有边界路由器的 BGP 状态"

Agent 步骤:
1. parse_inspection_scope("all 边界路由器")
   → 基于知识库识别 role:edge

2. nornir_bulk_execute(
       devices=["R-Edge-1", "R-Edge-2"],
       commands=[
           "show ip bgp summary",
           "show ip bgp neighbors",
           "show ip route bgp | count"
       ],
       max_workers=5
   )

3. 分析结果:
   - 检查所有 BGP 邻居状态是否为 Established
   - 统计接收/宣告路由数量
   - 识别异常邻居
   - 检查路由表大小

4. generate_report(template="bgp-audit", results=results)
```

### 预期输出
```
✅ BGP 审计完成

审计范围: 2 台边界路由器
审计时间: 2025-01-08 15:00

BGP 邻居汇总:
  R-Edge-1:
    ✅ 65001 (ISP1) - Established, 2h15m
    ✅ 65002 (ISP2) - Established, 2h15m
    ✅ 65003 (ISP3) - Established, 2h10m
    接收路由: 1,250 条 / 宣告路由: 450 条

  R-Edge-2:
    ✅ 65001 (ISP1) - Established, 2h20m
    ✅ 65004 (ISP4) - Established, 2h05m
    ⚠️  65002 (ISP2) - Idle (Connection refused) ← 异常
    接收路由: 1,100 条 / 宣告路由: 380 条

异常项:
  ⚠️  R-Edge-2 到 ISP2 (65002) 邻居状态为 Idle
     可能原因: 对端拒绝连接、配置错误、ACL 阻塞

建议措施:
  1. 检查 R-Edge-2 到 ISP2 的网络连通性
  2. 验证 BGP 配置 (邻居 AS、密码)
  3. 检查防火墙/ACL 规则
  4. 联系 ISP2 确认其端配置

报告已生成: .olav/reports/bgp-audit-20250108.html
```
