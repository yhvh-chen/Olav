# 🤖 OLAV - 企业级网络运维 AI 助手

**版本**: v0.8.0
**状态**: ✅ 生产就绪 (Production Ready)

OLAV 是一款专为网络工程师设计的先进 AI 助手。它结合了大型语言模型 (LLM) 的能力与企业级网络自动化工具，帮助您诊断、配置和监控网络基础设施。

**[English Guide](../README.MD)** | **中文指南**

---

## 🚀 快速开始

### 1. 安装

前置条件: Python 3.10+

```bash
# 推荐使用 uv 进行安装 (速度更快)
pip install uv
uv sync
```

### 2. 配置

创建您的配置文件:

```bash
cp .env.example .env
# 编辑 .env 文件，填入您的 API Key (OpenAI, Anthropic 等) 以及设备凭据
```

### 3. 启动

启动交互式命令行界面 (CLI):

```bash
uv run olav.py
```

---

## ✨ 核心功能

### 🧠 智能诊断
使用自然语言描述网络问题。OLAV 会分析问题，制定计划，并通过连接设备进行调查。
* "为什么 R1 上的 OSPF 一直翻滚？"
* "检查 Core-Switch-01 上是否有接口错误"

### 🔍 搜索与研究
集成了网络搜索和本地知识库查找功能，辅助故障排查。
* `/search "cisco bgp error code 123"` - 搜索在线文档 (DuckDuckGo)
* `/search "internal vlan policy"` - 搜索本地知识库
* 当本地知识不足时，自动回退到网络搜索。

### 🛠️ 交互式 CLI
功能强大的命令行界面，支持持久化历史记录和自动补全。
* `/help` - 显示可用命令
* `/devices` - 列出已连接的网络设备
* `/skills` - 查看可用的 AI 能力 (Skills)
* `/history` - 查看命令历史

### 🌐 多厂商支持
原生支持主流网络设备厂商。由于底层采用 Nornir/Netmiko，**理论上支持所有兼容 SSH 的网络设备**。
- Cisco (IOS, NX-OS)
- Huawei (VRP)
- Juniper (Junos)
- Arista (EOS)
- *任何 Netmiko 支持的设备*

### 🎨 个性化定制
定制您的 CLI 体验。
- **横幅 (Banner)**: 选择内置横幅 (雪人, DeepAgents) 或创建公司专属横幅。
- **设置**: 配置 `.olav/settings.json` 以调整 Agent 行为。

---

## 📖 用户指南

### 自然语言交互
只需输入您的需求。OLAV 使用 Markdown 定义的 "技能 (Skills)" 来理解您的意图并执行复杂的工作流。

> "备份所有接入层交换机的运行配置"
> "审计边界路由器的 BGP 配置并检查不一致之处"

### 核心 Slash 命令
快速访问系统功能：

| 命令 | 说明 |
|---------|-------------|
| `/analyze` | 启动 MicroAnalyzer 子智能体进行深度诊断 |
| `/inspect` | 对设备执行快速健康巡检 (L1-L4) |
| `/backup` | 触发配置备份工作流 |
| `/search` | 搜索知识库和网络信息 |
| `/devices` | 显示设备清单和连接状态 |
| `/skills` | 列出已加载的能力和策略 |
| `/memory` | 检查 Agent 的短期记忆 |
| `/clear` | 清屏 |
| `/quit` | 退出 OLAV |

### 配置管理
OLAV 允许您进行深度定制以适应您的环境。

#### 1. LLM 设置 (首次运行)
编辑您的 `.env` 文件以配置 AI 后端：
```ini
LLM_PROVIDER=openai  # openai, azure, 或 ollama
LLM_API_KEY=sk-proj-...
LLM_MODEL_NAME=gpt-4-turbo
# 可选: Nornir 配置文件路径
NORNIR_CONFIG_FILE=config/nornir_config.yaml
```

#### 2. 添加厂商命令与 TextFSM
要支持新的 CLI 命令，请将它们添加到 `.olav/imports/commands/` 下的白名单文件中（如 `cisco_ios.txt`）。

**配置规则：**
- `show version`: 允许执行
- `!copy run start`: 需要 **人工审批 (HITL)** 才能执行
- `#show version`: **临时禁用**。相当于该命令未被加载到可用工具集中。
- **全局黑名单**: **安全拦截**。在 `.olav/imports/commands/blacklist.txt` 中的命令会被强制拒绝。
    > *注意: 黑名单优先级高于白名单。即使有人错误地将 `reload` 加入了白名单，黑名单机制依然会阻止其执行。*

**自定义 TextFSM 解析 (节省 Token):**
OLAV 默认使用 `ntc-templates`。为了优化性能并减少 LLM Token 消耗：
1. 将自定义 `.template` 文件放入 `.olav/config/textfsm/`。
2. 在 `.olav/config/textfsm/index` 中建立映射。
结构化数据 (JSON) 比原始文本更容易被 LLM 这个，也更省钱。

#### 3. 知识库集成
OLAV 遵循 **"文档即真理 (Documents as Truth)"** 的设计哲学：来自本地知识库的答案优先级高于 LLM 的通用训练数据。

- **添加知识**: 将 Markdown (`.md`) 文件放入 `.olav/knowledge/` 目录。
- **建立索引**: 运行索引脚本进行向量化：
  ```bash
  uv run python scripts/index_knowledge.py --source local --path .olav/knowledge/
  ```
- **移除知识**: 删除文件并重新运行索引脚本（或使用 `--init` 重建数据库）。
- **使用**: 使用 `/search` 命令查询，系统将优先从您的文档生成答案。

#### 4. 横幅定制
编辑 `config/banners.py` 以更改 CLI 的外观和感觉。

---

## 🏗️ 架构概览

OLAV 基于 **DeepAgents** 框架构建，具有独特的 **三层知识架构**：

1.  **技能 (Skills / HOW)**: 以 Markdown 定义的策略和标准操作程序 (SOP)。
2.  **知识 (Knowledge / WHAT)**: 环境事实、站点代码和历史解决方案。
3.  **能力 (Capabilities / CAN)**: 经过验证的工具定义和 CLI 命令白名单 (Cisco/Huawei 等)。

这种设计确保了 AI 在安全、预定义的边界内运行，同时保持学习新任务的灵活性。

---

## 📄 许可协议与支持

**许可**: MIT License
**文档**: 详见 `docs/` 文件夹。
**反馈**: 如遇 Bug 或有功能建议，请在 GitHub 提交 Issue。

---

## 🔧 高级定制指南

### 1. 扩展 Nornir 资产清单
OLAV 使用 Nornir 进行网络交互。要手动添加设备：
1. 打开 `.olav/config/nornir/hosts.yaml`。
2. 按照标准 Nornir SimpleInventory 格式添加设备条目：
   ```yaml
   Router01:
     hostname: 192.168.1.1
     groups: ["cisco_ios", "core"]
     data:
       site: "Beijing"
   ```
3. 或者，您可以在 `.olav/config/nornir/config.yaml` 中配置动态库存插件 (如 NetBox)。

### 2. 创建自定义技能 (Skills)
您可以通过在 `.olav/skills/` 目录下创建 Markdown 文件来教 OLAV 新的工作流。

**示例:** `.olav/skills/my-audit.md`
```markdown
---
name: VLAN 审计
description: 检查交换机间的 VLAN 配置一致性
version: 1.0.0
---

# VLAN 审计流程
1. 获取所需 VLAN 的检查清单。
2. 对 'access' 组中的每个交换机：
    a. 运行 `show vlan brief`
    b. 与需求进行对比。
3. 报告缺失的 VLAN。
```
保存后，当您要求 "审计 VLAN" 时，OLAV 会自动加载并使用此技能。

### 3. 从 Claude Code 迁移
如果您有来自 Claude Code 或兼容 Agent 的现有技能：
1. 将您的技能文件复制到 `.olav/skills/`。
2. 运行迁移工具以标准化格式：
   ```bash
   uv run python scripts/migrate_to_claude_code.py
   ```
这将确保您的技能与 OLAV 引擎完全兼容。
