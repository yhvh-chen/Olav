# OLAV v0.8 Configuration Architecture - 单一权威源

## 问题陈述

之前存在**配置混乱**的问题：
- ❌ `.env.example` 包含已淘汰的服务（PostgreSQL、Redis、OpenSearch）
- ❌ `config/settings.py` 有 150+ 个字段，其中大多数是 v0.5 遗留
- ❌ `.olav/settings.json` 与 `config/settings.py` 重复配置
- ❌ 用户不知道该以哪个文件为准

## 解决方案：权威源确定

### 🎯 **v0.8 配置的单一权威源**

```
┌─────────────────────────────────────────────────────────────┐
│           OLAV v0.8 配置权威源 (Configuration Authority)     │
└─────────────────────────────────────────────────────────────┘

优先级（从高到低）：

1️⃣  config/settings.py ← 🏆 主权威源（Python runtime）
   └─ 定义所有配置字段的类型、默认值、验证规则
   └─ 通过 Pydantic 提供完整的类型检查和验证
   └─ 这是代码在运行时加载的唯一配置源

2️⃣  .env 文件 ← 用户本地覆盖（环境变量）
   └─ 通过环境变量覆盖 config/settings.py 的默认值
   └─ 用户特定的机密（API_KEY、密码）
   └─ 不提交到 git（在 .gitignore 中）
   └─ 复制自 .env.example 并编辑

3️⃣  .env.example ← 模板和文档
   └─ 新用户的参考
   └─ 所有可配置选项的说明
   └─ 提交到 git，用于 onboarding

4️⃣  .olav/settings.json ← DeepAgents 专用配置（READ-ONLY）
   └─ 仅供参考，不影响 Python 配置加载
   └─ 用于定义 OLAV Agent 的元数据
   └─ 不重复定义环境配置
```

## v0.8 架构移除的配置

以下配置已从 v0.8 中**完全移除**（因为不在新架构中使用）：

### ❌ PostgreSQL（已淘汰）

**理由**: v0.8 使用 DuckDB 代替
- v0.5: PostgreSQL（LangGraph checkpointer，OpenSearch indexing）
- v0.8: DuckDB（轻量本地数据库，能力缓存）

**移除的字段**:
```python
# 不再使用
postgres_host: str
postgres_port: int
postgres_user: str
postgres_password: str
postgres_db: str
postgres_uri: str
```

### ❌ Redis（已淘汰）

**理由**: v0.8 没有分布式缓存需求
- v0.5: Redis（session store, 缓存）
- v0.8: 单机模式，不需要

**移除的字段**:
```python
redis_url: str
redis_host: str
redis_port: int
redis_password: str
```

### ❌ OpenSearch（已淘汰）

**理由**: v0.8 使用 DuckDB 完全替代
- v0.5: OpenSearch（向量搜索、日志索引）
- v0.8: DuckDB（简单 SQL 查询，索引在内存或文件中）

**移除的字段**:
```python
opensearch_host: str
opensearch_port: int
opensearch_username: str
opensearch_password: str
opensearch_url: str
```

## v0.8 核心配置（保留的字段）

### ✅ LLM Configuration（LLM 配置）
```python
llm_provider: Literal["openai", "ollama", "azure"]  # LLM 提供商
llm_api_key: str                                   # API 密钥
llm_model_name: str                                # 模型名称
llm_temperature: float                             # 温度参数
llm_max_tokens: int                                # 最大 tokens
llm_base_url: str                                  # 自定义 endpoint
```

### ✅ Embedding Configuration（嵌入模型）
```python
embedding_provider: Literal["openai", "ollama"]   # 嵌入提供商
embedding_model: str                              # 模型
embedding_api_key: str                            # API 密钥
```

### ✅ Database Configuration（数据库）
```python
duckdb_path: str                                  # DuckDB 能力库路径
                                                  # 示例: .olav/capabilities.db
```

### ✅ Network Device Configuration（网络设备）
```python
netbox_url: str                                   # NetBox SSoT URL
netbox_token: str                                 # NetBox API token
netbox_verify_ssl: bool                           # SSL 验证
netbox_device_tag: str                            # 标签过滤

device_username: str                              # SSH 用户名
device_password: str                              # SSH 密码
device_enable_password: str                       # Enable 密码
device_timeout: int                               # 连接超时（秒）
```

### ✅ Application Settings（应用）
```python
olav_mode: Literal["QuickTest", "Production"]    # 运行模式
log_level: str                                    # 日志级别
guard_enabled: bool                               # 网络相关性守卫

nornir_ssh_port: int                              # SSH 端口
netconf_port: int                                 # NETCONF 端口
```

## 配置文件对应关系

| 配置来源 | 优先级 | 用途 | 提交 Git | 包含密钥 |
|---------|--------|------|---------|---------|
| `config/settings.py` | 🏆 最高 | 类型定义 + 默认值 | ✅ 是 | ❌ 否 |
| `.env` | 🥈 高 | 用户本地值 | ❌ 否 | ✅ 是 |
| `.env.example` | 🥉 参考 | 模板 + 说明 | ✅ 是 | ❌ 否 |
| `.olav/settings.json` | ❌ 无关 | Agent 元数据 | ✅ 是 | ❌ 否 |

## 如何添加新配置字段

### 1. 修改源头（config/settings.py）
```python
class Settings(BaseSettings):
    # 添加新字段
    new_setting: str = "default_value"  # 必须有类型提示和默认值
```

### 2. 更新文档（.env.example）
```env
# ============================================================================
# New Feature Configuration
# ============================================================================

NEW_SETTING=your-value-here
```

### 3. 用户本地配置（.env）
```env
NEW_SETTING=user-specific-value
```

### ❌ **不要在以下地方添加**:
- ❌ `.olav/settings.json` - 这是 DeepAgents 元数据，不是环境配置
- ❌ `.olav/OLAV.md` - 这是 Agent 指令，不是配置

## 验证配置清晰性

使用此命令验证配置是否清晰：

```bash
# 检查配置是否成功加载（无旧字段错误）
uv run python -c "from config.settings import settings; print('✅ OK')"

# 查看当前配置值
uv run python -c "from config.settings import settings; print(vars(settings))" | head -20
```

## 总结

### 🎯 **配置权威源确定**
- **主源**: `config/settings.py`（Python class 定义）
- **覆盖**: `.env`（用户本地环境变量）
- **文档**: `.env.example`（模板和说明）

### ✅ **v0.8 架构清晰**
- DuckDB（本地数据库）
- LLM + Embedding（AI 模型）
- NetBox（设备清单）
- Nornir（网络执行）
- DeepAgents（Agent 框架）

### ❌ **已移除的服务**
- PostgreSQL（用 DuckDB 替代）
- Redis（单机不需要）
- OpenSearch（用 DuckDB 替代）

---

**结论**: 以 `config/settings.py` 为准，其他文件为辅助。配置系统已清晰化，无歧义。
