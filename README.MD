# OLAV v0.8 项目说明

## 项目结构

```
.
├── .olav/                    # OLAV 核心配置和知识库 (Claude Code 兼容)
│   ├── OLAV.md              # 核心指令文档
│   ├── settings.json        # 配置文件
│   ├── config/              # 运行时配置
│   ├── skills/              # 技能定义 (Markdown)
│   ├── knowledge/           # 知识库 (Markdown)
│   ├── commands/            # 扩展脚本
│   ├── imports/             # 能力定义
│   │   ├── apis/            # REST API 定义
│   │   └── commands/        # CLI 命令定义
│   └── capabilities.db      # DuckDB 能力缓存 (生成)
│
├── src/olav/                # OLAV v0.8 Python 实现
│   ├── core/                # 核心模块 (LLM, Prompt, etc)
│   ├── tools/               # 工具实现 (NETCONF, CLI, etc)
│   └── execution/           # 执行后端 (Nornir, etc)
│
├── tests/                   # 单元测试和集成测试
│
├── CODE_REUSE_ANALYSIS.md   # 旧代码复用指南
├── DESIGN_V0.8.md           # 详细设计文档
└── archive/v0.5/            # 旧代码备份 (不再维护)
```

## 快速开始

1. **配置环境**
   ```bash
   uv sync --dev
   cp .env.example .env
   ```

2. **启动 OLAV**
   ```bash
   uv run src/olav/main.py
   ```

3. **定制 OLAV**
   - 编辑 `.olav/skills/*.md` 添加技能
   - 编辑 `.olav/knowledge/*.md` 添加知识
   - 编辑 `.olav/imports/apis/*.yaml` 添加 API

## 相关文档

- [DESIGN_V0.8.md](DESIGN_V0.8.md) - 完整设计文档
- [CODE_REUSE_ANALYSIS.md](CODE_REUSE_ANALYSIS.md) - 旧代码复用指南
- [.olav/OLAV.md](.olav/OLAV.md) - OLAV 核心指令
