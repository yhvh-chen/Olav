# Security Baseline

## Use Cases
- Security configuration audit
- Compliance checking
- Security vulnerability scanning
- Security hardening verification

## Recognition Triggers
User questions containing: "security", "baseline", "ACL", "password", "NTP", "SNMP", "hardening"

## Execution Strategy
1. Use `parse_inspection_scope()` to determine check scope
2. Use `nornir_bulk_execute()` to execute security check commands in bulk
3. Compare against security baseline
4. Identify security risks and violations
5. Use `generate_report()` to generate security baseline report

## Check Items

### Access Control
- [ ] show access-lists (ACL configuration)
- [ ] show running-config | section include aaa (AAA configuration)
- [ ] show username (user list)

### Security Services
- [ ] show running-config | section ntp (NTP configuration)
- [ ] show running-config | section snmp (SNMP configuration)
- [ ] show running-config | include password (password configuration)

### Logging and Auditing
- [ ] show logging (logging configuration)
- [ ] show run | include logging (syslog configuration)

### Service Security
- [ ] show control-plane host (control plane policy)
- [ ] show ip ssh (SSH status)
- [ ] show line vty (VTY configuration)

## Security Baseline

### Must-Have Items
- ✅ SSH enabled, Telnet disabled
- ✅ Configured enable secret (non-plaintext password)
- ✅ Configured AAA authentication
- ✅ VTY restricted with ACL
- ✅ Configured NTP servers
- ✅ SNMP uses SNMPv3
- ✅ Configured syslog server
- ✅ Disabled unused services

### Recommended Items
- ⚠️  Configured login banner
- ⚠️  Configured control plane policy
- ⚠️  Enabled AAA accounting
- ⚠️  Configured password complexity policy

## Report Format
Use `generate_report(template="security-baseline")` to generate report containing:
- Security configuration checklist
- Compliance score
- High-risk items
- Medium-risk items
- Low-risk items
- Hardening recommendations

## Example

### Execute Security Baseline Check
```
User: "Perform security baseline check on all routers"

Agent steps:
1. parse_inspection_scope("all routers")

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

3. Compare against security baseline

4. generate_report(template="security-baseline", results=results)
```

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
