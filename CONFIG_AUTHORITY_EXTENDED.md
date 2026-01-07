# OLAV v0.8 配置权威源详解

## 问题：.olav/settings.json vs config/settings.py

用户发现在 `.olav/settings.json` 中也有 LLM 和数据库配置，询问到底以哪个为准。

## 快速答案

**🏆 config/settings.py 是唯一的权威源。**

`.olav/settings.json` 中的配置是 **DeepAgents 框架元数据**，仅供参考，**不影响运行时实际配置**。

## 配置值对比表

| 配置项 | .olav/settings.json | config/settings.py | .env 实际值 | 生效的是？ |
|-------|-------------------|------------------|-----------|---------|
| **LLM Provider** | openai | openai | openai | ✅ config/settings.py + .env |
| **LLM Model** | gpt-4-turbo | gpt-4-turbo | x-ai/grok-4.1-fast | ✅ config/settings.py + .env |
| **LLM Base URL** | 无 | 空字符串 | https://openrouter.ai/api/v1 | ✅ config/settings.py + .env |
| **Temperature** | 0.1 | 0.1 | 0.1 | ✅ config/settings.py |
| **Max Tokens** | 4096 | 4096 | 4096 | ✅ config/settings.py |
| **DuckDB Path** | .olav/capabilities.db | .olav/capabilities.db | .olav/capabilities.db | ✅ config/settings.py + .env |

## 运行时配置加载流程

```
应用启动
  │
  ├─→ ① 加载 config/settings.py（默认值）
  │        └─ llm_model_name: "gpt-4-turbo"
  │        └─ duckdb_path: ".olav/capabilities.db"
  │        └─ ...其他所有字段...
  │
  ├─→ ② 读取 .env 环境变量
  │        └─ LLM_MODEL_NAME=x-ai/grok-4.1-fast
  │        └─ LLM_BASE_URL=https://openrouter.ai/api/v1
  │
  ├─→ ③ 环境变量覆盖默认值
  │        └─ 最终: llm_model_name = "x-ai/grok-4.1-fast"
  │        └─ 最终: llm_base_url = "https://openrouter.ai/api/v1"
  │
  └─→ ④ .olav/settings.json ？
           └─ ❌ 此时此刻不加载
           └─ ❌ 不影响任何配置
           └─ ❌ 仅是 agent 元数据文件
```

## 文件职责对比

### config/settings.py - 权威配置源 ✅

```python
class Settings(BaseSettings):
    llm_provider: Literal["openai", "ollama", "azure"] = "openai"
    llm_model_name: str = "gpt-4-turbo"           # ← 默认值
    llm_base_url: str = ""                         # ← 默认值
    llm_temperature: float = 0.1                   # ← 默认值
    duckdb_path: str = ".olav/capabilities.db"    # ← 默认值
```

**特点：**
- Python Pydantic 类，提供类型检查
- 在应用启动时加载
- 通过 .env 环境变量被覆盖
- 是**实际运行时使用的配置**

### .olav/settings.json - Agent 元数据 📖

```json
{
  "agent": {
    "name": "OLAV",
    "version": "0.8"
  },
  "llm": {
    "model": "gpt-4-turbo",
    "temperature": 0.1
  },
  "capabilities": {
    "db_path": ".olav/capabilities.db"
  }
}
```

**特点：**
- JSON 格式，结构化但静态
- 为 DeepAgents 框架提供 agent 定义信息
- 运行时**不加载**
- 仅用于文档和 agent 描述
- 应与 config/settings.py 默认值一致（最佳实践）

## 最佳实践

### ✅ DO 做什么

1. **需要改变配置？** 编辑 `.env`
   ```dotenv
   LLM_MODEL_NAME=x-ai/grok-4.1-fast
   LLM_BASE_URL=https://openrouter.ai/api/v1
   DUCKDB_PATH=.olav/capabilities.db
   ```

2. **添加新的全局默认值？** 编辑 `config/settings.py`
   ```python
   new_feature_enabled: bool = False
   ```

3. **更新 .env.example？** 保持与 config/settings.py 同步
   ```dotenv
   # Optional: description of the setting
   NEW_FEATURE_ENABLED=false
   ```

4. **保持 .olav/settings.json 一致？** 只是为了文档整洁
   - 更新 agent 元数据时确保版本号一致
   - 示意值应该与 config/settings.py 默认值相同

### ❌ DON'T 不要做什么

1. **❌ 不要在 .olav/settings.json 中改变配置值期望应用使用它**
   - 应用不会读取这个文件
   - 改了也没用

2. **❌ 不要在 .olav/settings.json 中存储敏感信息（API 密钥）**
   - 这是 agent 元数据，可能被发布
   - 敏感信息放在 .env（已 gitignore）

3. **❌ 不要同时在两个地方维护配置**
   - 只在 config/settings.py 定义字段
   - 只在 .env 提供用户值
   - .olav/settings.json 只用来记录默认值（参考）

## 常见问题

**Q: 为什么 .olav/settings.json 中有重复的配置？**

A: 因为它是 DeepAgents 框架所需的 agent 定义文件。框架需要知道 agent 的名称、版本、描述等。我们在这个文件中包含示意性的配置值，这样有人查看 agent 定义时能看到默认值是什么。但**运行时实际使用的配置来自 config/settings.py + .env**。

---

**Q: 如果 .olav/settings.json 和 config/settings.py 中的值不一样会怎样？**

A: 应用会使用 `config/settings.py + .env` 的值。`.olav/settings.json` 不影响运行。但为了保持文档一致性，建议保持同步。

---

**Q: 我改了 .olav/settings.json 中的 LLM 配置为什么没有生效？**

A: 因为应用不读取这个文件。需要改 `.env` 或 `config/settings.py` 才能生效。

---

**Q: 生产环境中 .olav/settings.json 有什么作用？**

A: 仅用于文档和 agent 管理。如果有 agent orchestration 系统，它可能会读取这个文件来理解 agent 的元数据。但运行时配置仍来自 `config/settings.py + .env`。

## 总结

| 文件 | 权威性 | 运行时使用 | 修改频率 | 何时编辑 |
|-----|------|---------|--------|---------|
| **config/settings.py** | ✅✅✅ 主权威 | ✅ 加载并使用 | 中等 | 添加新字段 |
| **.env** | ✅✅ 用户覆盖 | ✅ 加载并使用 | 频繁 | 改变配置值 |
| **.env.example** | ✅ 文档 | ❌ 不加载 | 中等 | 与 settings.py 同步 |
| **.olav/settings.json** | 📖 仅参考 | ❌ 不加载 | 很少 | 保持一致性 |
