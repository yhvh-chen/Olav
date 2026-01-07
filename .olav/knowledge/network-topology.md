# Network Topology Knowledge

## Lab Network Topology

### Device Inventory

#### Core Routers
| Device Name | IP Address | Role | Platform | Site |
|-------------|-----------|------|----------|------|
| R1 | 192.168.100.101 | Core Router | cisco_ios | border@lab |
| R2 | 192.168.100.102 | Border Router | cisco_ios | border@lab |
| R3 | 192.168.100.103 | Core Router | cisco_ios | core@lab |
| R4 | 192.168.100.104 | Core Router | cisco_ios | core@lab |

#### Core Switches
| Device Name | IP Address | Role | Platform | Site |
|-------------|-----------|------|----------|------|
| SW1 | 192.168.100.105 | Core Switch | cisco_ios | core@lab |
| SW2 | 192.168.100.106 | Core Switch | cisco_ios | core@lab |

#### Access Switches
| Device Name | IP Address | Role | Platform | Site |
|-------------|-----------|------|----------|------|
| SW3 | 192.168.100.107 | Access Switch | cisco_ios | access@lab |

### Device Connections

#### Core Layer Connections
```
R1 (192.168.100.101)
├─ Ethernet0/0 → R2.Ethernet0/0 (10.255.0.0/30)
├─ Ethernet0/1 → R3.Ethernet0/0 (10.255.0.4/30)
├─ Ethernet0/2 → SW1.Ethernet0/0
└─ Ethernet0/3 → Management Interface (192.168.100.101)

R2 (192.168.100.102)
├─ Ethernet0/0 → R1.Ethernet0/0
├─ Ethernet0/1 → R4.Ethernet0/0 (10.255.0.8/30)
├─ Ethernet0/2 → SW2.Ethernet0/0
└─ Ethernet0/3 → Management Interface (192.168.100.102)

R3 (192.168.100.103)
├─ Ethernet0/0 → R1.Ethernet0/1
├─ Ethernet0/1 → R4.Ethernet0/1 (10.255.0.12/30)
└─ Ethernet0/3 → Management Interface (192.168.100.103)

R4 (192.168.100.104)
├─ Ethernet0/0 → R2.Ethernet0/1
├─ Ethernet0/1 → R3.Ethernet0/1
└─ Ethernet0/3 → Management Interface (192.168.100.104)
```

#### Switch Layer Connections
```
SW1 (192.168.100.105)
├─ Ethernet0/0 → R1.Ethernet0/2
├─ Ethernet0/1 → SW2.Ethernet0/1 (Port-Channel1)
├─ Ethernet0/2 → SW3.Ethernet0/0
└─ Ethernet0/3 → Management Interface (192.168.100.105)

SW2 (192.168.100.106)
├─ Ethernet0/0 → R2.Ethernet0/2
├─ Ethernet0/1 → SW1.Ethernet0/1 (Port-Channel1)
└─ Ethernet0/3 → Management Interface (192.168.100.106)

SW3 (192.168.100.107)
├─ Ethernet0/0 → SW1.Ethernet0/2
├─ Ethernet0/1-24 → End devices
└─ Ethernet0/3 → Management Interface (192.168.100.107)
```

### IP Address Planning

#### Management Subnet
- **Subnet**: 192.168.100.0/24
- **Gateway**: 192.168.100.1 (assumed)
- **Purpose**: Device management
- **Access**: SSH from 192.168.100.1

#### Interconnect Subnet (P2P Links)
| Connection | Subnet | Purpose |
|------------|--------|---------|
| R1-R2 | 10.255.0.0/30 | Core interconnect |
| R1-R3 | 10.255.0.4/30 | Core interconnect |
| R2-R4 | 10.255.0.8/30 | Core interconnect |
| R3-R4 | 10.255.0.12/30 | Core interconnect |

#### Loopback Addresses
| Device | Loopback0 | Purpose |
|--------|-----------|---------|
| R1 | 1.1.1.1/32 | Router ID, Management IP |
| R2 | 2.2.2.2/32 | Router ID, Management IP |
| R3 | 3.3.3.3/32 | Router ID, Management IP |
| R4 | 4.4.4.4/32 | Router ID, Management IP |

### VLAN Planning

| VLAN ID | Name | Subnet | Gateway | Purpose |
|---------|------|--------|---------|---------|
| 10 | Office | 10.1.10.0/24 | 10.1.10.1 | Office area |
| 20 | Production | 10.1.20.0/24 | 10.1.20.1 | 生产区 |
| 30 | Guest | 10.1.30.0/24 | 10.1.30.1 | 访客区 |

### 路由协议

#### OSPF配置
- **进程ID**: 1
- **区域**: 0 (骨干区域)
- **Router ID**: 1.1.1.1 (R1), 2.2.2.2 (R2), etc.
- **网络发布**:
  - 192.168.100.0/24 (管理网段)
  - 10.255.0.0/22 (互联网段)
  - Loopback网络

### 服务配置

#### DNS
- **服务器**: 8.8.8.8, 8.8.4.4 (公网DNS)
- **域**: lab.local

#### NTP
- **服务器**: pool.ntp.org

#### SNMP
- **Community**: public (read-only)
- **版本**: SNMPv2c

### 设备组分类

#### 按角色分组
- **border**: R1, R2 (边界路由器)
- **core**: R3, R4, SW1, SW2 (核心设备)
- **access**: SW3 (接入交换机)

#### 按站点分组
- **border@lab**: R1, R2
- **core@lab**: R3, R4, SW1, SW2
- **access@lab**: SW3

### 访问凭证
- **用户名**: cisco
- **密码**: 见 `.env` 文件 (NORNIR_PASSWORD)
- **特权密码**: 见 `.env` 文件

## 拓扑图 (ASCII)

```
                    ┌─────────┐
                    │   ISP   │
                    └────┬────┘
                         │
                    ┌────┴────┐
                    │   R2    │ (Border)
                    │  .102   │
                    └────┬────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────┴────┐      ┌────┴────┐      ┌────┴────┐
   │   R1    │      │   R3    │      │   R4    │
   │  .101   │──────│  .103   │──────│  .104   │
   └────┬────┘      └────┬────┘      └────┬────┘
        │                │                │
   ┌────┴────┐           │           ┌────┴────┐
   │   SW1   │           │           │   SW2   │
   │  .105   │───────────┴───────────│  .106   │
   └────┬────┘       (Core Layer)    └────┬────┘
        │                               │
   ┌────┴────┐                          │
   │   SW3   │ (Access)                 │
   │  .107   │                          │
   └─────────┘                          │
        │                               │
   ┌────┴────┐                    ┌─────┴─────┐
   │ Users   │                    │  Servers  │
   └─────────┘                    └───────────┘
```

## 重要提示
1. 这是实验网络拓扑,用于OLAV开发和测试
2. 所有IP地址、设备名、角色信息可从Nornir inventory获取
3. 新增设备需同步到 `.olav/config/nornir/hosts.yaml`
4. 拓扑变更需更新此文档

## 更新记录
- **2026-01-07**: 创建初始拓扑文档,基于实验室环境
