# 设备别名 (Device Aliases)

Agent 在执行命令前应查阅此文件，将用户使用的别名转换为实际设备名、IP或接口。

## 使用说明
- 当用户提到这些别名时，自动替换为实际值
- 支持设备名、IP地址、接口名、VLAN等多种类型
- 如果用户使用了新的别名，询问含义后更新此文件

## 别名表

| 别名 | 实际值 | 类型 | 平台 | 备注 |
|------|--------|------|------|------|
| 核心交换机 | sw1, sw2 | device | cisco_ios | 核心层交换机 |
| SW1 | 192.168.100.105 | device | cisco_ios | Core Switch 1 |
| SW2 | 192.168.100.106 | device | cisco_ios | Core Switch 2 |
| 核心路由器 | r1, r2 | device | cisco_ios | 核心层路由器 |
| R1 | 192.168.100.101 | device | cisco_ios | Area 1 Core Router |
| R2 | 192.168.100.102 | device | cisco_ios | Area 1 Border Router |
| R3 | 192.168.100.103 | device | cisco_ios | Core Router |
| R4 | 192.168.100.104 | device | cisco_ios | Core Router |
| 边界路由器 | r3, r4 | device | cisco_ios | 边界层路由器 |
| 主链路 | ethernet0/0, ethernet0/1 | interface | - | 主要链路接口 |
| 管理接口 | ethernet0/3 | interface | - | 管理网络接口 |
| 环回接口 | loopback0 | interface | - | 环回地址接口 |
| 办公网 | VLAN 10 | vlan | - | 办公区域 |
| 生产网 | VLAN 20 | vlan | - | 生产区域 |
| 访客网 | VLAN 30 | vlan | - | 访客区域 |

## 使用示例

### 示例1: 设备别名
用户: "查看核心交换机的CPU使用率"
Agent 解析:
- 别名: "核心交换机" → 10.1.1.1
- 执行: nornir_execute("10.1.1.1", "show processes cpu")

### 示例2: 接口别名
用户: "上海专线的状态"
Agent 解析:
- 设备: R1 (10.1.1.1)
- 接口: "上海专线" → GigabitEthernet0/0/1
- 执行: nornir_execute("10.1.1.1", "show interface GigabitEthernet0/0/1")

### 示例3: VLAN别名
用户: "办公网有多少用户"
Agent 解析:
- VLAN: "办公网" → VLAN 100
- 执行: nornir_execute("10.1.1.1", "show vlan brief | include 100")

## 扩展规则

### 学习新别名
当用户首次提到未知别名时:
1. 询问: "请问'XX'是指哪台设备/接口?"
2. 用户回答后，更新此文件
3. 确认类型: device, interface, vlan, etc

### 多设备别名
一组设备可以用列表表示:
| 别名 | 实际值 | 类型 | 平台 |
|------|--------|------|------|
| 核心设备 | R1, R2, CS1, CS2 | device_list | cisco_ios |

### 地理位置别名
| 别名 | 实际值 | 类型 | 备注 |
|------|--------|------|------|
| 上海 | site:shanghai | site | 上海分部 |
| 北京 | site:beijing | site | 北京分部 |

## 注意事项
- 别名应该简洁明了
- 避免使用容易混淆的别名
- 定期清理不再使用的别名
- 保持与实际网络环境同步
