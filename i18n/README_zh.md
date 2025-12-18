# OLAV (NetAIChatOps)

<div align="center">

```
   ____  _        ___     __
  / __ \| |      / \ \   / /
 | |  | | |     / _ \ \ / / 
 | |  | | |    / ___ \ V /  
 | |__| | |___/ ___ \ | |   
  \____/|_____/_/   \_\|_|  
                            
  NetAIChatOps CLI
```

**企业级网络运维 ChatOps 平台**

[English](../README.md) | [中文版](README_zh.md)

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../LICENSE)

</div>

---

## 🤖 什么是 OLAV?

OLAV 是一款专为**通过自然语言操作大规模网络**而设计的 **ChatOps 工具**。它赋予网络工程师通过简单的对话即可管理数千台设备的能力——从多厂商路由器到交换机。

无论您需要“检查所有核心路由器的 BGP 状态”还是“诊断 R1 的丢包问题”，OLAV 都能将您的意图转化为精确、安全且可执行的网络命令。它使用 **LangGraph** 进行复杂工作流编排，利用 **SuzieQ** 进行可观测性分析，并以 **NetBox** 作为单一真理源 (SSoT)。

## 🌟 高级功能

### 🧠 智能代理 RAG 与架构感知
OLAV 通过实现**架构感知 (Schema-Aware) 架构**，超越了简单的 RAG：

- **动态工具注册**：OLAV 不再为每个网络表硬编码 120 多个工具，而是使用 **2 个通用工具**，动态查询 SuzieQ 和 OpenConfig 模式。LLM 会实时“学习”架构，以构建精确的查询。
- **三层知识库**：
  1. **情境记忆 (Episodic Memory)**：召回过去成功的工作流和意图到 XPath 的映射。
  2. **架构索引 (Schema Index)**：来自 YANG 模型和 Avro 模式的真理源。
  3. **文档索引 (Docs Index)**：厂商手册和 RFC 文档。

### 🛡️ 安全与治理
- **人机协同 (HITL)**：“安全第一”的哲学。所有写操作（NETCONF/CLI）都会触发中断，需要操作员审批。
- **漏斗式诊断**：自动将问题范围从宏观（全网 SuzieQ分析）缩小到微观（设备级 NETCONF 诊断）。
- **细粒度访问控制**：实现双令牌系统（Master/Session），通过基于角色的权限严格区分管理注册与操作执行。
- **查询守卫 (可选)**：基于 LLM 的预过滤器，拒绝非网络查询（防止提示词注入攻击）。默认禁用，可通过 `ENABLE_GUARD_MODE=true` 开启。
- **命令黑名单**：对 `config/command_blacklist.txt` 中定义的危险命令（如 `reload`、`format`）执行强制拦截，作为最后一道安全防线。

### 🌐 多厂商支持
- **无厂商锁定**：基于开放标准（NETCONF/YANG、OpenConfig）和厂商无关的驱动程序构建。
- **广泛的兼容性**：支持 **Nornir/Netmiko** 支持的任何设备（Cisco IOS/NX-OS、Juniper Junos、Arista EOS、华为等）。
- **统一数据模型**：使用 SuzieQ 将异构网络数据归一化为一致的模式，允许在混合厂商环境中进行统一查询。

### 🔄 优雅降级机制
- **自适应执行**：优先使用结构化数据（OpenConfig/NETCONF）以保证可靠性。
- **自动降级**：如果 NETCONF 失败或不可用，会自动降级到 CLI 屏幕抓取（TextFSM），无需人工干预。
- **弹性操作**：确保即使在仅部分支持自动化的旧设备上也能完成任务。

## 💡 核心场景

### 🚀 快速路径诊断
- **即时状态检索**：对常见查询（如“显示 R1 上的接口”）绕过复杂的推理。
- **低延迟**：通过直接查询 SuzieQ 数据湖，提供亚秒级响应。

### 🕵️ 深度故障分析
- **递归调查**：当检测到高级别问题（如“BGP 会话中断”）时，OLAV 会自动生成子代理来调查 1-3 层（接口错误 → ARP/ND → 路由表）。
- **根因识别**：跨设备关联事件，以精确定位故障源。

### 🛡️ 自动化智能巡检
- **主动健康检查**：针对“黄金状态”定义运行计划内或按需的审计。
- **日志异常检测**：分析 syslog 流，以检测不会触发 SNMP Trap 的静默失败或间歇性问题。
- **合规性验证**：确保配置与 NetBox 中的设计意图匹配。

## 🚀 快速开始

### 前提条件
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (极速 Python 包管理器)
- Docker & Docker Compose

### 安装

1. **克隆与设置**
   ```bash
   git clone https://github.com/yourusername/Olav.git
   cd Olav
   
   # 安装依赖
   uv sync --dev
   ```

2. **配置**
   ```bash
   # 1. 环境变量
   cp .env.example .env
   # 编辑 .env 以设置您的 LLM API 密钥和 NetBox 凭据
   
   # 2. 资产清单设置
   cp config/inventory.example.csv config/inventory.csv
   # 编辑 inventory.csv 以添加您的初始种子设备。
   # 提示：使用 'tags' 列指定协议偏好：
   #      - 'cli': 强制使用 CLI/TextFSM (例如旧设备)
   #      - 'openconfig': 优先使用 NETCONF/OpenConfig (如果支持则为默认)
   ```

3. **启动基础设施**
   ```bash
   docker-compose up -d
   ```

4. **初始化与运行**
   ```bash
   # Windows
   .\setup.ps1
   
   # Linux/Mac
   ./setup.sh
   
   # 启动 CLI
   uv run olav
   ```

## 🎮 CLI 使用指南

### 交互模式
启动聊天会话以进行即时查询和操作。
```bash
uv run olav
```

### 专家模式
对于需要递归调查的复杂故障排除（例如“为什么 R1 上的 BGP 在抖动？”），请使用专家模式。这将启用 **DeepDiveWorkflow**，它可以自动生成子代理来调查多个层级（L1-L3）。

```bash
uv run olav -e "诊断 Core-Switch-01 上的间歇性丢包"
# 或者
uv run olav --expert "检查 DataCenter-A 中的 BGP 异常"
```

### 自动化巡检
运行在 YAML 配置文件中定义的声明式健康检查。

1. **定义巡检配置文件**:
   在 `config/inspections/` 中创建或编辑 YAML 文件。
   
   *示例 `config/inspections/daily_check.yaml`:*
   ```yaml
   name: daily_check
   type: device-check
   devices:
     netbox_filter: { role: "core" }
   checks:
     - name: "BGP State"
       table: bgp
       assert: "state == 'Established'"
   ```

2. **管理巡检**:
   ```bash
   # 列出可用配置文件
   uv run olav inspect list
   
   # 运行特定配置文件
   uv run olav inspect run daily_check
   
   # 检查任务状态
   uv run olav inspect jobs
   ```

## 🔒 分布式架构与安全

OLAV 专为企业级规模和安全而设计：

### 服务端-客户端分离
- **解耦设计**：承担重任的核心服务器 (LangGraph/LLM) 集中运行，而轻量级客户端 (CLI) 可以部署在任何地方。
- **灵活部署**：在安全飞地/VPC 中运行服务器，并将客户端分发给运维团队。

### 🔐 零信任安全模型
- **令牌分离**：
  - **Master Token**：服务器启动时自动生成，用于客户端注册。
  - **Session Tokens**：颁发给每个客户端设备的唯一、可撤销令牌。
- **基于角色的访问**：`admin` (跳过 HITL) | `operator` (需要 HITL) | `viewer` (只读)。

## 🔑 令牌管理

**服务器启动** (自动生成 Master Token):
```bash
docker-compose up -d
# 在日志中打印 Master Token: docker-compose logs olav-app | grep "Master Token"

# 或者在 .env 中为多工作节点模式设置固定令牌:
# OLAV_API_TOKEN=<您的安全令牌>
```

**客户端注册** (带角色):
```bash
# 注册为 operator (默认，写操作需要 HITL)
olav register -n my-laptop -t <MASTER_TOKEN> --server http://<SERVER>:<PORT>

# 注册为 admin (可以跳过 HITL)
olav register -n admin-station -t <MASTER_TOKEN> --role admin --server http://<SERVER>:<PORT>

# 注册为 viewer (只读)
olav register -n monitoring-client -t <MASTER_TOKEN> --role viewer --server http://<SERVER>:<PORT>

# 验证
olav status
```

**会话管理** (服务端):
```bash
uv run olav token list              # 列出所有已注册的客户端
uv run olav token revoke <name>     # 撤销某个客户端的访问权限
```

## 💻 CLI 客户端部署

OLAV 支持两种部署模式：**本地 CLI** (完整环境) 和 **远程 CLI** (轻量级客户端)。

### 本地 CLI (完整环境)
当直接在 OLAV 服务器或具有完整环境的开发机上运行时使用此模式。

```bash
# 启动交互模式
uv run olav

# 单次查询
uv run olav -q "检查 R1 上的 BGP 状态"

# 专家模式 (深度钻取)
uv run olav -e "诊断 Core-Switch-01 上的丢包"
```

### 远程 CLI (轻量级客户端)
适用于需要连接到远程 OLAV 服务器而无需安装完整环境的操作员。

**安装:**
```bash
# 从 PyPI 安装 (发布后)
pip install olav-client

# 或从源码安装
cd client/
uv pip install .
```

**配置:**

服务器 URL 和端口取决于您的 OLAV 服务器部署。检查您的 `.env` 文件：
- `OLAV_SERVER_PORT_EXTERNAL` - 服务器暴露的外部端口 (默认: `18000`)

```bash
# 通过环境变量设置服务器 URL
export OLAV_SERVER_URL=http://<SERVER_IP>:${OLAV_SERVER_PORT_EXTERNAL}

# 或使用配置文件: ~/.olav/config.toml
cat > ~/.olav/config.toml << EOF
[server]
url = "http://your-server:18000"  # 匹配您的 .env OLAV_SERVER_PORT_EXTERNAL
timeout = 300
EOF
```

**注册客户端:**
```bash
# 首次注册 (需要管理员提供的 Master Token)
olav register -n my-laptop -t <MASTER_TOKEN> --server http://<SERVER_IP>:<PORT>
```

**使用:**
```bash
# 交互式聊天循环
olav

# 单次查询
olav -q "显示 R1 上的接口"

# 检查连接性和自动补全
olav status
```

### 部署模式对比

| 功能 | 本地 CLI (`uv run olav`) | 远程 CLI (`olav-client`) |
|---------|---------------------------|---------------------------|
| 安装 | 完整环境 + 依赖 | 轻量级 pip 包 |
| 网络访问 | 直接访问设备 | 通过 OLAV 服务器 API |
| 专家模式 | ✅ 支持 | ✅ 支持 |
| 巡检 | ✅ 完全访问 | ✅ 通过服务器 |
| 使用场景 | 服务器/开发机 | 操作员工作站 |

## 📄 授权协议

本项目采用 MIT 许可证 - 详情请参阅 [LICENSE](../LICENSE) 文件。
