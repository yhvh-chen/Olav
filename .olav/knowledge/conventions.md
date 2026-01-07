# Network Naming Conventions

This document defines naming standards for network devices, IP planning, VLAN allocation, etc., to help Agent understand network structure.

## Device Naming Standards

### Switch Naming
- `CS-<city>-<number>`: Core Switch
  - Example: CS-SH-01, CS-BJ-01
- `DS-<city>-<floor>-<number>`: Distribution Switch
  - Example: DS-SH-1F-01, DS-BJ-2F-01
- `AS-<city>-<floor>-<number>`: Access Switch
  - Example: AS-SH-1F-01, AS-BJ-3F-01

### Router Naming
- `R-<city>-<number>`: Router
  - Example: R-SH-01, R-BJ-01
- `Edge-<city>-<number>`: Edge Router
  - Example: Edge-SH-01

### Firewall Naming
- `FW-<location>-<number>`: Firewall
  - Example: FW-DMZ-01, FW-EDGE-01

## IP Address Planning

### Management Subnet
| Purpose | Subnet | Gateway | Description |
|---------|--------|---------|-------------|
| Device Management | 10.255.0.0/24 | 10.255.0.1 | All device management IPs |
| OOB Management | 192.168.100.0/24 | 192.168.100.1 | Out-of-band management |

### Business Subnet
| Location | Subnet | Purpose |
|----------|--------|---------|
| Headquarters | 10.1.0.0/16 | Headquarters office and production |
| Shanghai Branch | 10.2.0.0/16 | Shanghai branch |
| Beijing Branch | 10.3.0.0/16 | Beijing branch |
| Data Center | 10.10.0.0/16 | Data center servers |

### Interconnect Subnet
| Type | Subnet | Description |
|------|--------|-------------|
| Core Interconnect | 10.254.0.0/24 | Core device interconnect |
| Distribution Interconnect | 10.254.1.0/24 | Distribution device interconnect |
| Access Uplink | 10.254.2.0/24 | Access uplink |

## VLAN Planning

| VLAN Range | Purpose | Description |
|------------|---------|-------------|
| 1 | Management | Device management VLAN |
| 2-99 | Reserved | Reserved VLANs |
| 100-199 | Office | Office networks |
| 200-299 | Production | Production networks |
| 300-399 | DMZ | DMZ area |
| 400-499 | Guest | Guest networks |
| 500-599 | IoT | IoT devices |
| 900-999 | Interconnect | Device interconnect VLANs |

### Common VLANs
| VLAN | Name | Purpose |
|------|------|---------|
| 1 | Management | Device management |
| 100 | Office-Default | Office network default |
| 101 | Office-Finance | Finance department |
| 102 | Office-Engineering | Engineering department |
| 200 | Production-App | Application servers |
| 201 | Production-DB | Database servers |
| 300 | DMZ-Public | DMZ public area |
| 301 | DMZ-Private | DMZ private area |

## Interface Naming Convention

### Ethernet Interfaces
- `GigabitEthernet0/0/1`: Gi0/0/1
- `TenGigabitEthernet0/1/1`: Te0/1/1
- `FortyGigE0/2/1`: Fo0/2/1

### Logical Interfaces
- `Loopback0`: Lo0
- `Vlan10`: Vlan10
- `Port-channel1`: Po1

### Dedicated Line Interfaces
- `Serial0/0/0:0`: S0/0/0:0
- `POS0/1/0`: POS0/1/0

## Routing Protocol Convention

### OSPF
- Process ID: 1
- Area 0: Backbone area
- Area 1-10: Normal areas
- Router ID: Use Loopback0 address

### BGP
- AS Number: 65000 (Headquarters), 65001 (Shanghai), 65002 (Beijing)
- Router ID: Use Loopback0 address
- Peer Groups: internal-peers, external-peers

## 安全约定

### 访问控制
- 只允许必要端口
- 禁止Telnet，强制SSH
- 禁止HTTP，强制HTTPS
- SNMP使用v3

### 密码策略
- 最小长度12字符
- 包含大小写字母、数字、特殊字符
- 每90天更换

## 命名规范用途

### 场景1: 理解设备角色
用户: "CS-SH-01 的状态"
Agent理解: 核心交换机，上海，01号

### 场景2: 网络定位
用户: "10.2.x.x 网段"
Agent理解: 上海分部网段

### 场景3: VLAN理解
用户: "VLAN 200"
Agent理解: 生产区网络

## 更新记录
- 2026-01-07: 初始版本

## 注意事项
- 本文档应与实际网络配置保持同步
- 修改命名约定前需评估影响
- 新设备添加时遵循命名规范
