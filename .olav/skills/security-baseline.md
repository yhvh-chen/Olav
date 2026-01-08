# Security Baseline (安全基线检查)

## 适用场景
- 安全配置审计
- 合规性检查
- 安全漏洞扫描
- 安全加固验证

## 识别标志
用户问题包含: "安全"、"基线"、"ACL"、"密码"、"NTP"、"SNMP"、"加固"

## 执行策略
1. 使用 `parse_inspection_scope()` 确定检查范围
2. 使用 `nornir_bulk_execute()` 批量执行安全检查命令
3. 对照安全基线检查配置
4. 识别安全风险和违规项
5. 使用 `generate_report()` 生成安全基线报告

## 检查项

### 访问控制
- [ ] show access-lists (ACL 配置)
- [ ] show running-config | section include aaa (AAA 配置)
- [ ] show username (用户列表)

### 安全服务
- [ ] show running-config | section ntp (NTP 配置)
- [ ] show running-config | section snmp (SNMP 配置)
- [ ] show running-config | include password (密码配置)

### 日志和审计
- [ ] show logging (日志配置)
- [ ] show run | include logging (syslog 配置)

### 服务安全
- [ ] show control-plane host (控制平面策略)
- [ ] show ip ssh (SSH 状态)
- [ ] show line vty (VTY 配置)

## 安全基线

### 必须项
- ✅ SSH 已启用，Telnet 已禁用
- ✅ 配置了 enable secret (非明文密码)
- ✅ 配置了 AAA 认证
- ✅ VTY 使用 ACL 限制访问
- ✅ 配置了 NTP 服务器
- ✅ SNMP 使用 SNMPv3
- ✅ 配置了 syslog 服务器
- ✅ 关闭未使用的服务

### 推荐项
- ⚠️  配置登录banner
- ⚠️  配置控制平面策略
- ⚠️  启用 AAA accounting
- ⚠️  配置密码复杂度策略

## 报告格式
使用 `generate_report(template="security-baseline")` 生成报告，包含：
- 安全配置检查清单
- 合规性评分
- 高风险项
- 中风险项
- 低风险项
- 加固建议

## 示例

### 执行安全基线检查
```
用户: "对所有路由器进行安全基线检查"

Agent 步骤:
1. parse_inspection_scope("all 路由器")

2. nornir_bulk_execute(
       devices=["R1", "R2", "R3", "R4", "R5"],
       commands=[
           "show ip ssh",
           "show running-config | section ntp",
           "show running-config | section snmp",
           "show access-lists",
           "show username",
           "show running-config | include password"
       ],
       max_workers=10
   )

3. 对照安全基线分析结果

4. generate_report(template="security-baseline", results=results)
```

### 预期输出
```
✅ 安全基线检查完成

检查范围: 5 台路由器
检查时间: 2025-01-08 17:00

合规性评分:
  R1: ⚠️  75/100 (中风险)
  R2: ✅ 90/100 (低风险)
  R3: ❌ 60/100 (高风险)
  R4: ✅ 85/100 (低风险)
  R5: ⚠️  70/100 (中风险)

高风险项 (需立即处理):
  ❌ R3: Telnet 仍启用 (端口 23)
     风险: 明文传输凭据
     建议: 立即禁用 Telnet，仅使用 SSH

  ❌ R5: 使用 SNMPv1/v2c
     风格: 明文传输 community string
     建议: 升级到 SNMPv3

  ❌ R1, R3, R5: 未配置 enable secret
     风险: enable 密码可能为明文
     建议: 配置 "enable secret <强密码>"

中风险项:
  ⚠️  R1: 未配置 NTP 服务器
     风险: 时间不同步可能影响日志审计
     建议: 配置 "ntp server <NTP服务器IP>"

  ⚠️  R3: VTY 未配置访问 ACL
     风险: 任何人都可能尝试登录
     建议: 配置 "access-class <ACL> in"

低风险项:
  ℹ️  R1, R5: 未配置登录 banner
     建议: 配置法律声明 banner

加固建议优先级:
  P0 (立即): R3 禁用 Telnet、R5 升级 SNMP、所有设备配置 enable secret
  P1 (本周): 配置 NTP、配置 VTY ACL
  P2 (本月): 配置 banner、启用 AAA accounting

报告已生成: .olav/reports/security-baseline-20250108.html
```
