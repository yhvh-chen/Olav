# OLAV迁移到Agent平台 - 完整操作指南

**最后更新:** 2026-01-09  
**支持平台:** Claude Code, Cursor IDE, 其他Agent平台

---

## 🎯 快速开始 (3步)

### 1️⃣ 测试迁移 (不修改文件)
```bash
cd /path/to/OLAV
python scripts/migrate_olav_to_agent.py --platform claude --dry-run
```

### 2️⃣ 执行迁移 (自动备份)
```bash
python scripts/migrate_olav_to_agent.py --platform claude
```

### 3️⃣ 验证迁移
```bash
python scripts/verify_claude_compatibility.py .
pytest tests/ -v
```

**完成!** ✅ 系统已迁移到Claude Code Skill格式

---

## 📋 详细操作步骤

### 步骤1: 准备工作

#### a) 检查系统状态
```bash
# 验证当前目录结构
ls -la .olav/
ls -la .olav/skills/
ls -la .olav/commands/
```

#### b) 检查Python环境
```bash
python --version  # 3.8+ 
which python      # 确认虚拟环境

# 如果未激活虚拟环境
source venv/bin/activate  # Linux/Mac
.venv\Scripts\Activate.ps1  # Windows PowerShell
```

#### c) 安装依赖 (如果需要)
```bash
uv add pyyaml
uv add langchain
uv add duckdb
```

### 步骤2: 执行迁移

#### 选项A: 迁移到Claude Code
```bash
python scripts/migrate_olav_to_agent.py --platform claude
```

输出示例:
```
🚀 开始迁移: claude
   工作目录: /path/to/OLAV
   Agent目录: .olav
   干运行模式: False

[1/7] 备份现有文件...
   备份 .olav → .backup_20260109_120000
   ✅ 备份现有文件 完成

[2/7] 迁移Skill目录结构...
   ✓ quick-query/SKILL.md
   ✓ device-inspection/SKILL.md
   ✅ 迁移Skill目录结构 完成

[3/7] 迁移Commands格式...
   ✓ batch-query.md
   ✓ list-devices.md
   ✅ 迁移Commands格式 完成

[4/7] 迁移系统指令...
   ✓ CLAUDE.md 创建
   ✅ 迁移系统指令 完成

[5/7] 更新硬编码路径...
   ✓ src/olav/agent.py
   ✓ src/olav/storage_tools.py
   ✅ 更新硬编码路径 完成

[6/7] 创建配置文件...
   ✓ .claude-code-config.json 创建
   ✅ 创建配置文件 完成

[7/7] 生成报告...
   ✓ 报告已保存: migration_report_20260109_120000.json
   ✅ 生成报告 完成

✅ 迁移完成!
   已执行 15 个操作
```

#### 选项B: 迁移到Cursor IDE
```bash
python scripts/migrate_olav_to_agent.py --platform cursor
```

#### 选项C: 同时迁移到多个平台
```bash
python scripts/migrate_olav_to_agent.py --platform all
```

### 步骤3: 验证迁移结果

#### a) 检查文件结构
```bash
# 应该看到新的目录结构
find .olav/skills -name "SKILL.md"
find .olav/commands -name "*.md"
ls -la CLAUDE.md
```

预期输出:
```
.olav/skills/quick-query/SKILL.md
.olav/skills/device-inspection/SKILL.md
.olav/skills/deep-analysis/SKILL.md
.olav/skills/config-backup/SKILL.md
.olav/commands/batch-query.md
.olav/commands/list-devices.md
...
CLAUDE.md
```

#### b) 快速兼容性检查
```bash
python scripts/verify_claude_compatibility.py .
```

预期输出:
```
🔍 Verifying Claude Code Compatibility...

📋 Checking CLAUDE.md...
  ✓ CLAUDE.md is valid

🎯 Checking Skills...
  ✓ quick-query/SKILL.md is valid
  ✓ device-inspection/SKILL.md is valid
  ✓ deep-analysis/SKILL.md is valid
  ✓ config-backup/SKILL.md is valid

⚙️  Checking Commands...
  ✓ batch-query.md is valid
  ✓ list-devices.md is valid
  ✓ smart-query.md is valid
  ✓ search-capabilities.md is valid
  ✓ nornir-execute.md is valid

🔐 Checking for hardcoded paths...
  ✓ No hardcoded .olav paths found

============================================================
Checks Passed: 15
Checks Failed: 0
Warnings: 0
============================================================

✅ All checks passed!
```

#### c) 完整迁移验证
```bash
python scripts/verify_migration_complete.py .
```

#### d) 运行测试套件
```bash
# 运行所有测试
pytest tests/ -v

# 或只运行特定测试
pytest tests/test_search_tool.py -v
pytest tests/e2e/ -v
```

### 步骤4: 集成到Agent平台

#### 对于Claude Code:

1. **复制CLAUDE.md**到Claude Code项目
   ```bash
   # CLAUDE.md包含所有工具和skill描述
   # 在Claude Code中，将其内容用作系统提示词
   ```

2. **配置skills目录**
   ```bash
   # .olav/skills/ 包含所有skill定义
   # Claude Code会自动发现 /skill_name notation
   ```

3. **配置commands目录**
   ```bash
   # .olav/commands/ 包含所有command定义
   # 在Claude Code中可用为 /command_name notation
   ```

#### 对于Cursor IDE:

1. **复制配置文件**
   ```bash
   cp .cursor-config.json your-cursor-project/
   ```

2. **在Cursor设置中启用**
   ```json
   {
     "olav.enableSkills": true,
     "olav.skillDirectory": ".olav/skills",
     "olav.systemPromptFile": "CLAUDE.md"
   }
   ```

#### 对于其他平台:

查看自动生成的配置文件:
- `.claude-code-config.json` - Claude Code配置
- `.cursor-config.json` - Cursor IDE配置

---

## 🔄 常见操作

### 1. 如果迁移出错怎么办?

#### 使用--dry-run测试
```bash
# 再次运行测试，不会修改文件
python scripts/migrate_olav_to_agent.py --platform claude --dry-run
```

#### 恢复备份
```bash
# 找到备份目录
ls -d .backup_*

# 恢复备份
rm -rf .olav
cp -r .backup_20260109_120000/.olav .olav
```

### 2. 添加新的Skill

迁移后新增skill:

```bash
# 创建新skill
mkdir -p .olav/skills/my-skill
cat > .olav/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
version: 1.0
type: skill
description: My new skill
---

# My Skill

Content here...
EOF
```

### 3. 添加新的Command

```bash
# 创建新command
cat > .olav/commands/my-command.md << 'EOF'
---
name: my-command
version: 1.0
type: command
description: My new command
---

# My Command

## Implementation

\`\`\`python
def main():
    pass
\`\`\`
EOF
```

### 4. 更新知识库

```bash
# 重新加载知识库
python .olav/commands/reload-knowledge.py --incremental

# 同步知识库
python .olav/commands/sync-knowledge.py --cleanup
```

---

## 📊 迁移检查清单

- [ ] 运行 `--dry-run` 测试迁移
- [ ] 执行实际迁移
- [ ] 验证 `.olav/skills/*/SKILL.md` 存在
- [ ] 验证 `.olav/commands/*.md` 存在  
- [ ] 验证 `CLAUDE.md` 在根目录
- [ ] 运行 `verify_claude_compatibility.py` 检查
- [ ] 运行 `verify_migration_complete.py` 检查
- [ ] 运行 `pytest tests/ -v` 测试套件
- [ ] 检查迁移报告文件 (`migration_report_*.json`)
- [ ] 备份已创建 (`.backup_*` 目录)
- [ ] 在Agent平台中测试集成

---

## 🔧 高级选项

### 自定义agent目录名
```bash
# 默认使用 .olav，可以改成其他名称
python scripts/migrate_olav_to_agent.py --platform claude --agent-dir .claude
python scripts/migrate_olav_to_agent.py --platform claude --agent-dir .cursor
```

### 跳过备份
```bash
# 如果确定不需要备份（不推荐）
python scripts/migrate_olav_to_agent.py --platform claude --no-backup
```

### 详细输出
```bash
python scripts/migrate_olav_to_agent.py --platform claude -v
```

### 指定工作目录
```bash
python scripts/migrate_olav_to_agent.py --platform claude --workspace /path/to/olav
```

---

## 📈 迁移后的项目结构

```
OLAV/
├── CLAUDE.md                          ← 系统指令 (新)
├── .claude-code-config.json           ← Claude配置 (新)
├── .cursor-config.json                ← Cursor配置 (新)
├── migration_report_*.json            ← 迁移报告 (新)
├── .backup_*/                         ← 备份目录 (新)
│
├── .olav/
│   ├── skills/
│   │   ├── quick-query/
│   │   │   └── SKILL.md              ← 新格式
│   │   ├── device-inspection/
│   │   │   └── SKILL.md              ← 新格式
│   │   ├── deep-analysis/
│   │   │   └── SKILL.md              ← 新格式
│   │   └── config-backup/
│   │       └── SKILL.md              ← 新格式
│   │
│   ├── commands/
│   │   ├── batch-query.md            ← Markdown格式 (新)
│   │   ├── list-devices.md           ← Markdown格式 (新)
│   │   ├── smart-query.md            ← Markdown格式 (新)
│   │   ├── search-capabilities.md    ← Markdown格式 (新)
│   │   ├── nornir-execute.md         ← Markdown格式 (新)
│   │   ├── search-knowledge.md       ← 新工具
│   │   ├── reload-knowledge.md       ← 新工具
│   │   └── sync-knowledge.md         ← 新工具
│   │
│   ├── knowledge/
│   │   ├── solutions/
│   │   └── *.md
│   │
│   └── data/
│       └── knowledge.db
│
├── config/
│   └── settings.py                   ← agent_dir 配置 (更新)
│
├── tests/
│   ├── test_search_tool.py           ← 新
│   ├── test_knowledge_indexer.py     ← 新
│   ├── test_claude_code_compat.py    ← 新
│   └── e2e/
│       ├── test_knowledge_e2e.py     ← 新
│       └── test_cli_integration.py   ← 新
│
└── src/olav/
    └── [所有.py文件已更新路径配置]
```

---

## 🚀 使用迁移后的系统

### 在Claude Code中

1. **加载系统指令**
   - 使用 `CLAUDE.md` 的内容作为系统提示词

2. **使用Skills**
   ```
   /quick-query "查询内容"
   /device-inspection "设备分析"
   /deep-analysis "深层分析"
   /config-backup "配置备份"
   ```

3. **使用Commands**
   ```
   /search-knowledge "搜索查询"
   /reload-knowledge
   /sync-knowledge
   ```

### 搜索知识库

```bash
# 混合搜索 (推荐)
python .olav/commands/search-knowledge.py "BGP configuration" --type hybrid

# 全文搜索
python .olav/commands/search-knowledge.py "BGP" --type full_text

# 向量搜索
python .olav/commands/search-knowledge.py "network issues" --type vector
```

### 管理知识库

```bash
# 重新加载/更新知识库
python .olav/commands/reload-knowledge.py --incremental

# 同步数据库 (检测删除等)
python .olav/commands/sync-knowledge.py --cleanup --report
```

---

## 📝 故障排除

### 问题1: "permission denied"
```bash
# 解决: 授予执行权限
chmod +x scripts/migrate_olav_to_agent.py
python scripts/migrate_olav_to_agent.py --platform claude
```

### 问题2: "ModuleNotFoundError"
```bash
# 解决: 安装依赖
uv add pyyaml
# 或
pip install pyyaml
```

### 问题3: 迁移部分失败
```bash
# 解决: 查看迁移报告
cat migration_report_*.json

# 手动恢复
rm -rf .olav
cp -r .backup_*/.olav .olav

# 重试迁移
python scripts/migrate_olav_to_agent.py --platform claude
```

### 问题4: 验证失败
```bash
# 检查具体问题
python scripts/verify_claude_compatibility.py . 
python scripts/verify_migration_complete.py .

# 查看详细日志
python scripts/verify_claude_compatibility.py . > verification.log
```

---

## 📞 获取帮助

### 查看迁移脚本帮助
```bash
python scripts/migrate_olav_to_agent.py --help
```

### 查看验证脚本帮助
```bash
python scripts/verify_claude_compatibility.py --help
python scripts/verify_migration_complete.py --help
```

### 查看迁移报告
```bash
# 最新的报告
cat $(ls -t migration_report_*.json | head -1)

# 查看所有操作
cat migration_report_*.json | jq '.actions'
```

---

## ✅ 总结

| 步骤 | 命令 | 说明 |
|------|------|------|
| 1 | `--dry-run` | 测试迁移 |
| 2 | `migrate_olav_to_agent.py` | 执行迁移 |
| 3 | `verify_claude_compatibility.py` | 验证格式 |
| 4 | `verify_migration_complete.py` | 验证完整性 |
| 5 | `pytest tests/` | 运行测试 |
| 6 | 在Agent中测试 | 集成验证 |

迁移完成后，您的OLAV系统就可以在Claude Code、Cursor或其他Agent平台上使用了! 🎉

---

**需要帮助?** 查看 `MIGRATION_COMPLETION_REPORT.md` 了解更多详情。
