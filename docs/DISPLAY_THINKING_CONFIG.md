# Display Thinking 配置指南

## 概述

`display_thinking` 是一个配置选项，用于控制 OLAV CLI 是否在处理查询时显示 LLM 的思考过程。

## 配置选项

### 默认值：`true`（启用）

## 使用方法

### 1. 通过环境变量（最高优先级）

```bash
# 启用显示思考过程
export DISPLAY_THINKING=true
uv run olav query "check device R1 ospf"

# 禁用显示思考过程
export DISPLAY_THINKING=false
uv run olav query "check device R1 ospf"
```

### 2. 通过 .env 文件

在项目根目录创建或编辑 `.env` 文件：

```env
# 启用思考过程显示（默认）
DISPLAY_THINKING=true

# 禁用思考过程显示
DISPLAY_THINKING=false
```

### 3. 通过 .olav/settings.json

编辑 `.olav/settings.json` 文件：

```json
{
  "display_thinking": true
}
```

## 优先级顺序

1. **环境变量** (最高优先级)
   ```bash
   export DISPLAY_THINKING=false
   ```

2. **.env 文件**
   ```
   DISPLAY_THINKING=false
   ```

3. **.olav/settings.json**
   ```json
   {"display_thinking": false}
   ```

4. **代码默认值** (最低优先级)
   - 默认为 `true`

## 显示效果

### 启用时（display_thinking=true）

```
OLAV> check all devices' ospf peer status
🔍 Processing...
🤔 Thinking...  # <- 显示思考进度
╭─ ⏳ smart_query | all ─╮
│ Processing...         │
╰────────────────────────╯
## OSPF Neighbor Status...
[最终结果]
```

### 禁用时（display_thinking=false）

```
OLAV> check all devices' ospf peer status
🔍 Processing...
╭─ ⏳ smart_query | all ─╮
│ Processing...         │
╰────────────────────────╯
## OSPF Neighbor Status...
[最终结果]
```

## 与 --verbose 标志的关系

- **--verbose 标志**：显示 LLM 的完整思考过程（暗灰色文本，逐 token 流式）
- **display_thinking 配置**：控制是否显示思考进度 spinner

### 组合效果

| 配置 | --verbose | 显示效果 |
|------|-----------|--------|
| true | false | 显示思考 spinner |
| true | true | 显示完整思考过程 + spinner |
| false | false | 不显示思考，只显示结果 |
| false | true | 只显示完整思考过程（来自 --verbose） |

## 配置文件参考

### src/olav/cli/cli_main.py

```python
# 读取配置
from config.settings import settings

show_thinking = settings.display_thinking or verbose
display = StreamingDisplay(verbose=verbose, show_spinner=show_thinking)
```

### config/settings.py

```python
class Settings(BaseSettings):
    # ...
    # CLI Display Settings
    display_thinking: bool = True
```

## 常见问题

### Q: 为什么默认启用？

A: 用户体验。显示思考过程能让用户知道 LLM 正在工作，而不是看起来像卡住了。

### Q: 可以在运行时改变吗？

A: 不能直接改变。但可以：
- 用环境变量启动新会话
- 编辑 .env 或 .olav/settings.json 再重启

### Q: display_thinking 和 --verbose 的区别？

A: 
- **display_thinking**: spinner 进度显示（快速反馈）
- **--verbose**: 完整的 token 级流式输出（调试用）

## 相关文件

- [CLI Main](src/olav/cli/cli_main.py): 流处理逻辑
- [Settings](config/settings.py): 配置定义
- [Streaming Display](src/olav/cli/display.py): 显示实现
- [LLM Streaming Guide](docs/LLM_STREAMING_GUIDE.md): 详细使用指南
