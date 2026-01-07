# OLAV v0.8 依赖管理

本项目使用 `uv` 进行快速的依赖管理和虚拟环境管理。

## 快速开始

### 1. 安装 uv

```bash
# 使用 pip 安装 uv
pip install uv

# 或从官网安装 (推荐)
# https://docs.astral.sh/uv/
```

### 2. 初始化项目

```bash
# 同步依赖（创建虚拟环境+安装包）
uv sync

# 包含开发依赖
uv sync --dev
```

### 3. 激活虚拟环境

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Linux/Mac
source .venv/bin/activate
```

## 常用命令

### 依赖管理

```bash
# 添加运行时依赖
uv add langchain

# 添加开发依赖
uv add --dev pytest

# 带版本约束
uv add "openai>=1.0,<2.0"

# 更新锁文件
uv lock

# 同步到虚拟环境
uv sync
```

### 运行代码

```bash
# 在虚拟环境中运行脚本
uv run main.py

# 运行测试
uv run pytest

# 代码检查
uv run ruff check src/
uv run mypy src/
uv run black src/
```

## 项目结构

```
.
├── pyproject.toml       # 项目配置和依赖定义
├── uv.lock             # 锁文件（由 uv 自动生成）
├── .venv/              # 虚拟环境（由 uv 创建）
├── src/olav/           # 源代码
├── tests/              # 测试
└── .olav/              # OLAV 配置和数据
```

## 疑难排解

### 虚拟环境问题

```bash
# 删除虚拟环境并重新创建
rm -r .venv
uv sync
```

### 版本冲突

```bash
# 清除锁文件并重新生成
rm uv.lock
uv lock
uv sync
```

## 参考

- [uv 官方文档](https://docs.astral.sh/uv/)
- [pyproject.toml 标准](https://packaging.python.org/specifications/pyproject-toml/)
