# 📂 Data 和 Knowledge Base 目录位置指南

根据 `CLAUDE_CODE_SKILL_MIGRATION.md` 的设计，这里是明确的回答：

---

## 核心设计原则

**Knowledge Base 应该放在哪里？** → **根目录 + Agent 目录**（分层）

**Data 应该放在哪里？** → **Agent 目录内**（`.{agent}/data/`）

---

## 具体结构（根据文档）

### 当前 OLAV 结构 vs 迁移后结构

| 类型 | OLAV 当前 | Claude Code 标准 | 说明 |
|------|-----------|-----------------|------|
| **System Prompt** | `.olav/OLAV.md` | `CLAUDE.md` (根目录) | 全局系统指令 |
| **小型知识文件** | `.olav/knowledge/` | `knowledge/` (根目录) | 别名、拓扑、约定等 |
| **大型知识库** | `.olav/data/knowledge.db` | `.{agent}/data/knowledge.db` | 向量化索引 |
| **数据文件** | `.olav/data/` | `.{agent}/data/` | 配置、日志、报告 |

---

## 详细的目录树

```
project-root/
├── CLAUDE.md                          ← 根目录（全局系统提示）
├── knowledge/                         ← 根目录（全局小型知识库）
│   ├── aliases.md                     # 设备别名映射
│   ├── conventions.md                 # 命名约定
│   └── solutions/                     # 故障排查方案
│
├── docs/                              ← 根目录（原始文档，用于索引）
│   ├── vendor/                        # 厂商文档
│   ├── wiki/                          # 团队 Wiki
│   └── runbooks/                      # 运维手册
│
├── .claude/  (可重命名为 .olav, .cursor, etc)
│   ├── settings.json                  # Agent 配置
│   ├── memory.json                    # Agent 记忆
│   └── data/                          ← Agent 目录内
│       ├── knowledge.db               # 向量化知识库（从 docs/ 索引而来）
│       ├── configs/                   # 设备配置文件
│       ├── logs/                      # 执行日志
│       └── reports/                   # 分析报告
│
├── commands/                          ← 根目录（Slash Commands）
│   ├── query.md
│   ├── inspect.md
│   └── search-docs.md
│
└── skills/                            ← 根目录（Skills）
    ├── quick-query/SKILL.md
    ├── device-inspection/SKILL.md
    └── deep-analysis/SKILL.md
```

---

## 关键点说明

### 1️⃣ **Knowledge Base 的分层设计**

文档中有明确说明（第二部分，2.1节）：

> **知识库设计**：大型文档（厂商手册、Wiki）索引到 `.{agent}/data/knowledge.db`，通过 `search()` 工具检索。小型元数据（别名、拓扑）保留在 `knowledge/` 目录。

这意味着：

```yaml
# 根目录的 knowledge/ 放小文件
knowledge/
  ├── aliases.md          # 250 字节
  ├── conventions.md      # 500 字节
  └── solutions/

# .{agent}/data/knowledge.db 放大型文档的向量化索引
.olav/data/
  └── knowledge.db        # 从 docs/vendor/, docs/wiki/ 索引而来
```

### 2️⃣ **Data 目录必须在 Agent 目录内**

表格中明确指出：

```
| `.olav/data/` | `.claude/data/` | `.{agent}/data/` (含 knowledge.db) |
```

因为：
- ✅ 支持多 Agent 同时使用（`.claude/`, `.olav/`, `.cursor/`）
- ✅ 每个 Agent 有独立的数据隔离
- ✅ 易于切换不同 Agent 环境

### 3️⃣ **为什么根目录要放 CLAUDE.md？**

文档 2.2 节的目录树明确显示：

```
project-root/
├── CLAUDE.md                          # 系统提示（从 .olav/OLAV.md 移动）
```

而不是：
```
.claude/CLAUDE.md  ❌ 错误
```

原因：
- `CLAUDE.md` 是全局的系统指令，所有 Agent 都共享
- `.{agent}/settings.json` 才是 Agent 特定的配置

---

## 迁移清单

如果要完整实施这个设计，需要做：

### Phase 1: 创建根目录结构
```bash
# 在根目录创建全局知识库
mkdir -p knowledge/solutions
mkdir -p docs/{vendor,wiki,runbooks}

# 将 OLAV.md 移动到根目录并重命名
mv .olav/OLAV.md CLAUDE.md

# 将知识文件移动到根目录
mv .olav/knowledge/* knowledge/
```

### Phase 2: 创建 Agent 目录结构
```bash
# 创建 Agent 目录（可重命名）
mkdir -p .claude/data/{configs,logs,reports}

# 保持 knowledge.db 在 Agent 目录
mv .olav/data/knowledge.db .claude/data/
mv .olav/data/configs/* .claude/data/configs/
```

### Phase 3: 迁移 Commands 和 Skills
```bash
# Commands 从 .olav 迁移到根目录
mkdir -p commands
mv .olav/commands/*.md commands/

# Skills 从 .olav 迁移到根目录
mkdir -p skills
# 使用 migrate_to_claude_code.py 脚本转换格式
python scripts/migrate_to_claude_code.py
```

---

## 配置文件对应关系

### 当前配置
```python
# config/settings.py
DATA_DIR = PROJECT_ROOT / "data"
AGENT_DIR = PROJECT_ROOT / ".olav"
```

### 迁移后配置
```python
# config/settings.py
DATA_DIR = AGENT_DIR / "data"  # 改为相对 Agent 目录
AGENT_DIR = PROJECT_ROOT / ".claude"  # 或通过环境变量配置
```

这样自动支持：
```bash
# 切换到不同 Agent
export AGENT_DIR=.olav    # 用 OLAV Agent
export AGENT_DIR=.claude  # 用 Claude Agent
export AGENT_DIR=.cursor  # 用 Cursor Agent
```

---

## 总结表格

| 类型 | 位置 | 说明 |
|------|------|------|
| **系统提示** | 根目录 `CLAUDE.md` | 全局，所有 Agent 共享 |
| **小型知识库** | 根目录 `knowledge/` | 别名、约定、快速参考 |
| **大型文档** | 根目录 `docs/` | 源文档，用于索引 |
| **向量化索引** | `.{agent}/data/knowledge.db` | Agent 级别隔离 |
| **运行数据** | `.{agent}/data/` | Agent 级别隔离 |
| **Commands** | 根目录 `commands/` | 全局，所有 Agent 共享 |
| **Skills** | 根目录 `skills/` | 全局，所有 Agent 共享 |

---

## 常见问题

**Q: Knowledge 和 Data 都要在根目录吗？**  
A: 不完全。小型知识文件在根目录 `knowledge/`，大型索引在 Agent 目录 `.{agent}/data/knowledge.db`

**Q: 如果用 .claude 或 .olav 哪个更好？**  
A: 可重命名，都可以。关键是使用 `settings.agent_dir` 配置，支持多 Agent

**Q: 现在的 data 目录需要改吗？**  
A: 最终设计是 `PROJECT_ROOT/data` → `.{agent}/data`，但可以渐进式迁移

**Q: Knowledge.db 一定要在 .olav/data 吗？**  
A: 根据设计是的。因为支持多 Agent 隔离
