# ☃️ OLAV - 企业网络运维 AI 助手

```
 ▄████▄   ██        ▄████▄    ██    ██
██▀  ▀██  ██       ██▀  ▀██   ██    ██
██    ██  ██       ████████   ██    ██
██▄  ▄██  ██       ██    ██    ██  ██
 ▀████▀   ████████ ██    ██    ████
```

**版本**: v0.8.0
**状态**: ✅ 生产就绪
**框架**: DeepAgents Native

OLAV（Operations Language-based Autonomous Vehicle）是一个智能的、**agentic** 网络助手，专为生产环境设计。它在**生成式 AI** 与**确定性网络自动化**（Nornir/Netmiko）之间架起了桥梁。

**[中文指南](README_ZH.md)** | **[English Guide](README.MD)**

---

## 🌟 为什么选择 OLAV？

### 🧠 Agentic 自主系统
基于 **DeepAgents** 框架构建，OLAV 不仅仅是一个聊天机器人。它是一个**目标导向的自主智能体**，可以：
- **规划**: 将复杂的请求（如"审计所有 BGP 邻居"）分解为推理链式的子任务。
- **执行**: 自主执行多步骤工作流程，独立使用工具并在继续前验证结果。
- **反思**: 根据预期 schema 验证输出，在失败时重试，并根据反馈调整策略。
- **记忆**: 在故障排除会话中保持上下文，从过往解决方案中学习，积累组织知识。
- **自我纠正**: 检测执行错误、分析根本原因，并自主调整战术 — 无需人工干预。

### 🔄 与 Claude Code 兼容
OLAV v0.8 采用与 **Claude Code** 100% 兼容的文件结构（`.claude/` ↔ `.olav/`）。
- **无缝迁移**: 若要与 Claude Code 配合使用，只需将 `.olav/` 复制到 `.claude/` 并将 `OLAV.md` 重命名为 `CLAUDE.md`。
- **标准化 SOP**: 使用标准 Markdown 定义健壮的操作流程，供智能体遵循。

### 📊 结构化输出解析
停止向 LLM 提供原始文本。
- **TextFSM 模板**: OLAV 自动通过 TextFSM 模板解析网络 CLI 输出，将非结构化文本流转换为**结构化 JSON schema**。
- **令牌高效**: 这种结构化解析方法使 AI 能够对 schema 字段（`interface[0].status`、`bgp[0].state`）进行推理，而不是解析原始文本，显著提高准确性并减少令牌使用。

### 🔐 Schema 感知的命令与 API
在执行边界处强制类型安全和参数验证。
- **命令参数**: 所有网络命令在执行前都会根据严格的 schema 进行验证 — 平台特定（Cisco、Juniper 等），具有类型化参数和验证规则。
- **API 验证**: RESTful API 和工具调用强制请求/响应 schema，防止格式错误的命令，并确保一致的输出结构用于下游处理。
- **类型安全**: 强类型在早期捕捉意图不匹配，减少运行时错误，提高智能体在自主执行中的可靠性。

### 🛡️ 企业级安全
- **3 层知识架构**: 分离**技能**（How）、**知识**（What）和**能力**（Tools）。
- **人机交互循环 (HITL)**: 敏感命令（`reload`、`config`）触发强制审批门槛 — 关键决策需要人工验证。
- **提示词保护**: 自动的意图过滤阻止非网络查询，防止提示词注入和离题请求。
- **命令白名单与黑名单**: 所有可执行命令均按平台（Cisco、Juniper 等）严格白名单管理，明确的黑名单阻止危险操作（reload、reboot、erase 等），防止意外或不当操作。
- **多厂商支持**: 原生支持 Cisco、Huawei、Juniper、Arista 及任何 SSH 兼容设备。

---

## 🚀 快速开始

### 1. 安装
前置条件：Python 3.11+（必需）

**选项 A：使用 uv（推荐 - 更快）**
```bash
# 安装 uv
pip install uv

# 安装依赖
uv sync

# 激活虚拟环境（可选，uv run 无需激活）
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows
```

**选项 B：使用 pip/virtualenv（标准方式）**
```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[dev]"
```

### 2. 配置（环境变量）
从模板创建配置文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件并填入你的设置：
```bash
# 必需：LLM 配置
LLM_PROVIDER=openai  # 或 'ollama' 用于本地模型
LLM_API_KEY=your-api-key-here  # 获取地址：https://platform.openai.com 或 https://openrouter.ai

# 可选：本地 Ollama
OLLAMA_BASE_URL=http://localhost:11434

# 可选：RAG 用的嵌入模型供应商
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest
```

### 3. 网络清单设置（关键）
OLAV 使用 Nornir 与网络设备通信。你必须在 `.olav/config/nornir/hosts.yaml` 中定义你的设备。
*注意：这是 OLAV 了解哪些设备存在的唯一途径。*

1. 复制示例文件：
   ```bash
   cp .olav/config/nornir/hosts.yaml.example .olav/config/nornir/hosts.yaml
   ```

2. 编辑 `hosts.yaml` 并填入实际的设备信息。**此文件已被 git 忽略**以保护凭证安全。

```yaml
# 示例 .olav/config/nornir/hosts.yaml
R1:  # <-- 在聊天中使用的别名（例如 "Check R1"）
  hostname: 192.168.10.1
  platform: cisco_ios
  username: admin
  password: password123
  groups: ["core", "routers"]
```

### 4. 初始化（一次性）
运行初始化脚本以自动设置所有组件：

**如果使用 uv：**
```bash
uv run python scripts/init.py
```

**如果使用 pip/venv：**
```bash
python scripts/init.py
```

**它会做什么：**
- ✅ 从 `.env` 值生成 `.olav/settings.json`（模型、温度等）
- ✅ 从 `hosts.yaml` 设备名称生成 `.olav/knowledge/aliases.md`
- ✅ 将命令白名单加载到 `capabilities.db`
- ✅ 为 RAG 搜索创建 `knowledge.db` schema

**其他选项：**
```bash
# 使用 uv
uv run python scripts/init.py --check           # 检查初始化状态
uv run python scripts/init.py --force           # 重新生成 settings.json 和 aliases.md
uv run python scripts/init.py --reload-commands # 编辑白名单后重新导入命令

# 使用 pip/venv
python scripts/init.py --check
python scripts/init.py --force
python scripts/init.py --reload-commands
```

### 5. 启动

**选项 A：使用 uv**
```bash
uv run olav
```

**选项 B：使用 pip/venv（激活后）**
```bash
olav
# 或
python -m olav
```

**选项 C：Docker（用于隔离或部署）**
```bash
# 使用 OpenAI/Azure（推荐）
docker-compose up olav

# 使用本地 Ollama LLM
docker-compose up

# 交互式运行
docker-compose run --rm olav

# 拉取最新 Ollama 模型
docker-compose exec ollama ollama pull llama3
```

---

## 🔒 安全特性

OLAV 实施**纵深防御**安全模型，以确保在生产网络中的安全自主运维。

### 1. **提示词保护** - 意图过滤
通过验证用户查询是网络运维相关的，防止提示词注入攻击和离题请求。

- **严格模式**: 仅允许明确的网络运维操作（例如"检查 BGP 状态"）
- **模糊匹配**: 智能分类以捕捉恶意提示词的各种变体
- **可配置**: 通过 `.olav/settings.json` 中的 `guard.enabled` 启用/禁用

```json
{
  "guard": {
    "enabled": true,
    "strict_mode": false
  }
}
```

### 2. **命令白名单** - 能力控制
所有可执行命令均按厂商平台严格白名单管理。OLAV **永远不会**执行不在白名单中的命令。

**白名单位置**: `.olav/imports/commands/{platform}.txt`

示例 `.olav/imports/commands/cisco_ios.txt`:
```
# 只读命令
show version
show interfaces
show running-config
# 默认被阻止：
# reload        ← 不在白名单中，已阻止
# write erase   ← 不在白名单中，已阻止
```

**优势**:
- 防止意外执行危险命令（reload、factory reset）
- 厂商特定：不同平台允许不同命令
- 易于审计：所有允许的命令在一个地方

添加新命令：编辑平台文件并运行：
```bash
uv run python scripts/init.py --reload-commands
```

### 2b. **命令黑名单** - 禁止操作
除了白名单外，OLAV 还维护一个明确的**黑名单**，其中的危险命令**始终**被禁止，无论白名单状态如何。

**黑名单位置**: `.olav/imports/commands/blacklist.txt`

示例禁止命令：
```
# 绝对禁止 - 无例外
reload
reboot
erase
format
delete filesystem
write erase
factory reset
shutdown
halt
```

**为什么两者都需要？**
- **白名单** = 明确权限（正面控制）- 仅允许列出的命令
- **黑名单** = 明确禁止（负面控制）- 即使被误白名单，这些也被禁止
- **纵深防御**: 双层保护防止意外配置错误

### 3. **人机交互循环 (HITL)** - 审批门槛
关键操作在执行前自动暂停以等待人工审批。

**需要审批的操作**:
- **写操作**: 任何修改设备状态的命令（config、reload）
- **技能更新**: 当智能体学习新的故障排除解决方案或设备别名时
- **风险诊断**: 需要人工签字的高影响诊断操作

**配置** (`.olav/settings.json`):
```json
{
  "hitl": {
    "require_approval_for_write": true,
    "require_approval_for_skill_update": true,
    "approval_timeout_seconds": 300
  }
}
```

**示例流程**:
```
用户: "更新 SW1 的 VLAN 配置"
智能体: 🔐 等待 - 这是一个写操作
        请确认：set vlan 100 name prod-vlan [Y/n]
用户: Y
智能体: ✅ 开始更新...
```

---

## 💻 工作流和 CLI

OLAV 在两种模式下运行：**自然语言**（Agentic）和**工作流**（Deterministic）。

### Agentic 聊天
描述你想要什么，智能体使用其技能规划执行。
> "检查为什么核心路由器上的 OSPF 在振荡"
> "审计 Access-01 和 Dist-01 之间的 VLAN 一致性"

### 工作流命令（`/`）
对于频繁的任务，使用斜杠命令触发**Schema 感知工作流**。这些比自由形式的聊天更快、更便宜（更少的令牌）且更可靠。

**详细用法：**

*   **`/analyze [query]`**: 启动 MicroAnalyzer 子智能体。
    *   *示例*: `/analyze "为什么 Core-01 上的 BGP 对等连接断开？"`
*   **`/inspect [target]`**: 运行健康检查（L1-L4）。
    *   *示例*: `/inspect group:core` 或 `/inspect R1`
*   **`/backup`**: 为所有/特定设备备份 running-config。
    *   *示例*: `/backup`（所有）或 `/backup group:access`

| 命令 | 描述 | Agentic 等级 |
|------|------|------------|
| `/analyze` | **深度诊断**: 启动 MicroAnalyzer 子智能体进行根本原因分析。 | ⭐⭐⭐ |
| `/inspect` | **健康检查**: 基于已知 schema 运行 L1-L4 检查。 | ⭐⭐ |
| `/backup` | **配置备份**: 用于保存 running-config 的标准化工作流。 | ⭐ |
| `/search` | **RAG 搜索**: 跨本地知识（.md）和网络的混合搜索。 | ⭐ |
| `/devices` | **清单**: 列出已连接设备及其连接状态。 | - |
| `/skills` | **技能清单**: 列出已加载的 Markdown SOP。 | - |
| `/stats` | **令牌使用**: 显示成本和令牌消耗统计。 | - |
| `/plan` | **调试**: 显示智能体的当前思维链和规划。 | - |
| `/clear` | 清屏。 | - |
| `/quit` | 退出。 | - |

---

## 🛠️ 高级特性

### 1. 添加技能（Claude Code 兼容）
在 `.olav/skills/` 中创建 Markdown 文件以教导新的标准操作流程（SOP）。OLAV 原生读取**Claude Code** 技能格式。

### 2. 配置 TextFSM 解析器
要教导 OLAV 如何解析新的网络命令：
1. 将 NTC 模板文件放入 `.olav/config/textfsm/`。
2. 更新 `.olav/config/textfsm/index` 中的索引文件。

OLAV 将自动使用模板将命令输出转换为 JSON，使智能体能够对结构化数据进行推理，而不是原始文本。

### 3. 添加工作流
将技能作为斜杠命令（工作流）公开：
1. 如上所述创建技能 markdown。
2. 在 `.olav/config/commands.yaml` 中注册它（或依赖自动加载器进行搜索）。
*注意：高优先级工作流如 `/analyze` 为性能而硬编码。*

### 4. 知识库（RAG）与标准路径
OLAV 遵循**"文档即真实"**哲学。

**默认文件位置：**
| 功能 | 输入/输出 | 路径 | 格式 |
|------|---------|------|------|
| **知识库** | 输入 | `.olav/knowledge/` | `.md`、`.txt`、`.pdf` |
| **报告** | 输出 | `.olav/reports/` | `.html`（仪表板）、`.json` |
| **技能** | 输入 | `.olav/skills/` | `.md`（Claude Code 格式） |
| **清单** | 输入 | `.olav/config/nornir/hosts.yaml` | YAML |

**用法：**
- 将本地站点文档放入 `knowledge/` 并运行 `uv run python scripts/index_knowledge.py`。
- 在 `reports/` 中找到生成的健康报告（来自 `/inspect` 或 `/analyze`）。

### 5. Agentic 自主学习
OLAV 可以从成功的故障排除会话和用户交互中学习：

**自动生成的内容：**
| 内容 | 路径 | 触发条件 |
|------|------|---------|
| **解决方案** | `.olav/knowledge/solutions/*.md` | 成功诊断后，智能体保存案例 |
| **设备别名** | `.olav/knowledge/aliases.md` | 用户澄清设备名称时（例如"核心路由器是 R1"） |

**示例 - 学习别名：**
```
用户: "核心交换机是 SW1 和 SW2"
智能体: ✓ 学习别名"核心交换机" → "SW1, SW2"
```
智能体会追加到 `aliases.md`，并在未来查询中使用此知识。

**示例 - 保存解决方案：**
解决 BGP 振荡问题后，智能体自动保存：
```markdown
# 案例：bgp-flapping-r1
> 创建于：2026-01-12（由 OLAV 自动保存）

## 问题
R1 上 BGP 邻居振荡...

## 根本原因
传输链接上的 MTU 不匹配...

## 解决方案
将 MTU 调整为 1500...
```

*注意：解决方案自动保存需要 settings.json 中的 `learning.autoSaveSolutions: true`*

---

## 🏗️ 架构

- **运行时**: Python 3.12 + `uv`
- **智能体框架**: DeepAgents
- **数据库**: DuckDB（向量 + 关系型）
- **执行**: Nornir（并发）+ Netmiko（SSH）
- **协议**: SSH、Telnet、NETCONF

## 📄 许可证与支持

**MIT 许可证** - 开源且企业就绪。
