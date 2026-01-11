# LLM Streaming Output 指南

## 概述

OLAV v0.8 支持分层流式输出，帮助用户查看 LLM 在处理查询时的工作过程。

## 两种输出模式

### 1. 紧凑模式（默认）

```bash
OLAV> check all devices' ospf peer status
🔍 Processing...
🤔 Thinking...  # <- 显示 LLM 正在思考
╭─ ⏳ smart_query | all ─╮
│ Processing...                 │
╰────────────────────────────────╯
## OSPF Neighbor Status...
[最终结果]
```

**特点：**
- 显示处理状态和工具执行
- 显示思考进度（旋转的 spinner）
- 显示最终结果
- 干净的输出，适合日常使用

### 2. 详细模式（Verbose）

```bash
OLAV> check all devices' ospf peer status --verbose
# 或在交互模式中：
OLAV> set verbose on
```

**特点：**
- 显示 LLM 的完整思考过程（暗灰色）
- 显示工具调用和执行
- 显示最终结果
- 适合调试和学习

## 使用方式

### 单条查询中启用 Verbose

```bash
uv run olav query "check device R1 ospf" --verbose
```

### 在交互模式中启用 Verbose

```bash
# 启动交互模式
uv run olav

# 然后在提示符处
OLAV> check device R1 ospf --verbose
```

## 流式输出的工作原理

### 处理流程

1. **初始化**：用户输入查询

2. **LLM思考**：
   - 紧凑模式：显示 "🤔 Thinking..." spinner
   - Verbose 模式：实时显示 LLM 的思考过程（暗灰色文本）

3. **工具执行**：
   - 显示工具名称、目标设备和命令
   - 例如：`[⏳ smart_query | all]`

4. **结果显示**：
   - 最终结果以格式化表格展示
   - 自动格式化 OSPF 邻接信息、配置等

### 事件处理

OLAV 使用 LangGraph 的 `astream()` API 实时处理事件：

```python
async for event in agent.astream(
    {"messages": messages}, 
    stream_mode="updates"  # 实时更新
):
    # 处理 LLM 输出
    # 处理工具调用
    # 处理最终结果
```

## 故障排除

### 问题：看不到任何 LLM 输出

**原因**：可能是 LLM 配置问题或网络问题

**解决方案**：
1. 检查 LLM 配置：`.olav/config/settings.json`
2. 确保 API 密钥正确设置
3. 检查网络连接

### 问题：输出显示 "Processing..." 但没有结果

**原因**：LLM 响应缓冲或超时

**解决方案**：
1. 增加超时时间（在 config 中）
2. 尝试更简单的查询
3. 使用 `--verbose` 查看详细信息

## 性能考虑

- **紧凑模式**：推荐用于日常使用（更快的显示）
- **Verbose 模式**：推荐用于调试和学习（更详细但可能较慢）

## 相关文件

- [StreamingDisplay 类](src/olav/cli/display.py)：显示逻辑
- [stream_agent_response()](src/olav/cli/cli_main.py)：流处理逻辑
- [单元测试](tests/unit/test_streaming_display.py)：功能验证
