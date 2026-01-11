# Inspection 和 Backup 输出配置说明

## 问题1：输出目录配置

### 简明回答
**是的，默认输出到 `data` 目录**，但更具体的结构如下：

### 详细目录结构

```
.olav/
├── data/
│   ├── configs/           ← Backup (device configurations)
│   ├── logs/              ← Logs and outputs
│   └── reports/           ← Inspection reports & analysis
├── knowledge/
│   └── solutions/         ← Troubleshooting solutions
└── scratch/               ← Temporary files
```

### 具体输出位置

#### 1. **Inspection 报告输出**
```
位置: .olav/data/reports/
格式: Markdown（默认）/ JSON / HTML（可配置）
命名: {timestamp}-{inspection_type}.md
示例: 20250109-l1-inspection.md
```

**源代码：**[inspection_tools.py#L312](src/olav/tools/inspection_tools.py#L312)
```python
output_path.parent.mkdir(parents=True, exist_ok=True)
# 默认输出到 .olav/data/reports/
```

#### 2. **Backup 输出**
```
位置: .olav/data/configs/
格式: 纯文本配置文件
命名: {device}-{config_type}-config-{timestamp}.txt
示例: R1-running-config-20250109-143022.txt
```

**源代码：**[storage_tools.py#L174-L207](src/olav/tools/storage_tools.py#L174)
```python
filepath = str(Path(settings.agent_dir) / "data" / "configs" / filename)
```

#### 3. **Tech-Support 输出**
```
位置: .olav/data/reports/
命名: {device}-tech-support-{timestamp}.txt
示例: R1-tech-support-20250109-143022.txt
```

### 配置位置

**主配置文件：**[config/settings.py#L37](config/settings.py#L37)
```python
DATA_DIR = PROJECT_ROOT / "data"
AGENT_DIR = PROJECT_ROOT / _agent_dir_name  # 默认 ".olav"
```

---

## 问题2：是否自动向量化到知识库

### 简明回答
**目前没有自动向量化**，但有基础的知识库存储框架。

### 详细说明

#### 当前状态
1. ✅ **有知识库框架**
   - 位置：`.olav/knowledge/`
   - 存储：解决方案、日志、配置等
   - 工具：`write_file()`, `read_file()`, `save_device_config()`

2. ❌ **没有自动向量化**
   - 没有向量化引擎集成
   - 没有自动嵌入处理
   - 没有向量数据库连接（如 Pinecone/Weaviate/Milvus）

3. ⚠️ **有向量化基础设施**
   - 配置了嵌入提供商：`EMBEDDING_PROVIDER = "ollama"`
   - 数据库支持：DuckDB（在 `.olav/data/capabilities.db`）
   - 但未被激活使用

#### 源代码证据

**存储工具：**[storage_tools.py#L20-40](src/olav/tools/storage_tools.py#L20)
```python
def _get_allowed_dirs() -> list[str]:
    """Get allowed directories based on agent_dir configuration."""
    agent_dir = settings.agent_dir
    return [
        f"{agent_dir}/data/configs",          # Device configurations
        f"{agent_dir}/data/logs",             # Logs and outputs
        f"{agent_dir}/knowledge/solutions",   # Troubleshooting solutions
        f"{agent_dir}/data/reports",          # Reports and analysis
        f"{agent_dir}/scratch",               # Temporary files
    ]
```

**嵌入配置：**[config/settings.py#L50-60]
```python
EMBEDDING_PROVIDER = 'ollama'  # 默认使用本地 Ollama
# 但没有被 inspection 或 backup 使用
```

**数据库：**[src/olav/core/database.py](src/olav/core/database.py)
```python
# DuckDB 存在但主要用于存储设备能力（capabilities）
# 不用于报告向量化
db_path: Path to DuckDB database file (defaults to agent_dir/data/capabilities.db)
```

---

## 建议方案

### 如果需要向量化 Inspection 报告，可以：

#### 方案 A：手动集成向量化（推荐）
```python
# 在 generate_report() 后添加向量化逻辑
from langchain.embeddings import OllamaEmbeddings
from langchain.vectorstores import Chroma

embeddings = OllamaEmbeddings(model="mistral")
vector_store = Chroma.from_texts(
    texts=[report_content],
    embedding=embeddings,
    persist_directory=".olav/vectors"
)
```

#### 方案 B：使用 Claude Code Skill（更好）
创建 `/vector-store` Workflow 来处理：
- 新报告检测
- 自动向量化
- 知识库更新

---

## 快速参考

| 项目 | 值 |
|------|-----|
| **Inspection 报告输出** | `.olav/data/reports/` |
| **Backup 输出** | `.olav/data/configs/` |
| **知识库位置** | `.olav/knowledge/` |
| **向量化状态** | ❌ 未启用 |
| **向量引擎** | Ollama (configured) |
| **数据库** | DuckDB (capabilities only) |
| **可配置吗？** | ✅ 是（通过 `settings.py`） |

---

## 文件位置参考

- 配置：[config/settings.py](config/settings.py)
- Backup 工具：[src/olav/tools/storage_tools.py](src/olav/tools/storage_tools.py)
- Inspection 工具：[src/olav/tools/inspection_tools.py](src/olav/tools/inspection_tools.py)
- 数据库：[src/olav/core/database.py](src/olav/core/database.py)

---

## 总结

1. **输出目录**：默认是 `data`（更准确说是 `.olav/data/`）
   - Inspection 报告 → `data/reports/`
   - Backup → `data/configs/`
   - 知识库 → `knowledge/`

2. **向量化**：目前没有自动集成
   - 有框架和配置但未激活
   - 可以手动添加向量化逻辑
   - 建议通过 Claude Code Skill 实现
