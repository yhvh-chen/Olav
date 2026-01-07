# OLAV Phase 1 MVP - 快速开始指南

## 状态：✅ 已完成

所有 Phase 1 里程碑测试都已通过。系统已准备好进行真实网络查询。

## 快速测试

### 运行所有 Phase 1 测试
```bash
cd c:\Users\yhvh\Documents\code\Olav
uv run pytest tests/e2e/test_phase1_mvp.py -v
```

**预期结果**: 5/5 PASSED (约 73 秒)

### 运行特定测试
```bash
# 列出所有设备
uv run pytest tests/e2e/test_phase1_mvp.py::TestPhase1QuickQuery::test_list_devices -v -s

# 查询接口状态
uv run pytest tests/e2e/test_phase1_mvp.py::TestPhase1QuickQuery::test_show_interface_r1 -v -s

# 获取设备版本
uv run pytest tests/e2e/test_phase1_mvp.py::TestPhase1QuickQuery::test_show_version -v -s

# 验证命令白名单
uv run pytest tests/e2e/test_phase1_mvp.py::TestPhase1QuickQuery::test_command_whitelist_enforcement -v -s
```

## 配置检查

### 验证 LLM 配置
```bash
uv run python -c "from config.settings import settings; \
  print(f'Provider: {settings.llm_provider}'); \
  print(f'Model: {settings.llm_model_name}'); \
  print(f'Base URL: {settings.llm_base_url}'); \
  print(f'API Key: {\"✅\" if settings.llm_api_key else \"❌\"}')"
```

**预期输出**:
```
Provider: openai
Model: x-ai/grok-4.1-fast
Base URL: https://openrouter.ai/api/v1
API Key: ✅
```

### 验证设备配置
```bash
uv run python -c "from olav.tools.network import list_devices; \
  print('Devices available'); \
  result = list_devices.invoke({}); \
  print(result)"
```

**预期输出**:
```
包含设备列表: R1, R2, R3
```

## 文件关键位置

| 文件 | 用途 | 修改权限 |
|------|------|--------|
| `.env` | 本地配置（API密钥、凭据） | 🔐 本地专用，不提交 |
| `config/settings.py` | 配置定义和默认值 | ⚙️ 更改需谨慎 |
| `.olav/config/nornir/` | Nornir 网络设备清单 | 📝 可根据实际设备更新 |
| `.olav/OLAV.md` | Agent System Prompt | 📝 可自定义行为 |
| `.olav/imports/commands/` | 命令白名单 | 🔒 控制可执行命令 |
| `tests/e2e/test_phase1_mvp.py` | Phase 1 E2E 测试 | 📖 参考用 |

## 核心配置

### .env 中的必需字段
```dotenv
# LLM 配置
LLM_PROVIDER=openai
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-...
LLM_MODEL_NAME=x-ai/grok-4.1-fast

# 设备凭据
DEVICE_USERNAME=cisco
DEVICE_PASSWORD=cisco

# 嵌入模型
EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://192.168.100.10:11434
```

### 设备清单 (.olav/config/nornir/hosts.yaml)
```yaml
hosts:
  R1:
    hostname: 192.168.100.101
    platform: cisco_ios
  R2:
    hostname: 192.168.100.102
    platform: cisco_ios
  R3:
    hostname: 192.168.100.103
    platform: cisco_ios
```

## 测试覆盖

| 测试 | 目标 | 状态 |
|------|------|------|
| test_list_devices | 设备清单加载 | ✅ PASSED |
| test_show_interface_r1 | 接口查询 | ✅ PASSED |
| test_show_version | 版本查询 | ✅ PASSED |
| test_command_whitelist_enforcement | 安全过滤 | ✅ PASSED |
| test_quick_query_sync | Agent 初始化 | ✅ PASSED |

## 常见问题

### Q: 测试失败，提示 API 密钥错误
**A**: 检查 `.env` 文件中的 `LLM_API_KEY` 是否正确设置。不要提交 .env 到 git。

### Q: 连接不到设备
**A**: 验证 `.olav/config/nornir/hosts.yaml` 中的设备 IP 和凭据是否正确。

### Q: Embedding 模型加载失败
**A**: 确保 Ollama 在 `http://192.168.100.10:11434` 运行，或更新 `.env` 中的 `EMBEDDING_BASE_URL`。

### Q: 测试很慢
**A**: 第一次 LLM 调用会初始化模型，之后会变快。异步测试通常需要 15-20 秒。

## 代码结构

```
src/olav/
├── agent.py              # 主 Agent 创建
├── main.py              # CLI 入口点
├── core/
│   ├── llm.py          # LLM 工厂（从 settings.py 读取配置）
│   └── database.py     # DuckDB 数据库
├── tools/
│   ├── network.py      # Nornir 执行工具
│   ├── capabilities.py # 能力查询工具
│   └── loader.py       # 能力加载工具
└── execution/
    └── backends/       # 执行后端

tests/
├── conftest.py         # 测试配置和 fixtures
├── e2e/
│   └── test_phase1_mvp.py  # Phase 1 E2E 测试
└── unit/
    └── ...             # 单元测试

config/
├── settings.py         # Pydantic 配置定义
└── ...其他配置文件

.olav/
├── OLAV.md            # Agent System Prompt
├── config/
│   ├── nornir/        # Nornir 配置和清单
│   └── ...
├── imports/
│   ├── commands/      # 命令白名单
│   └── apis/          # API 配置
├── skills/            # Agent Skills
├── knowledge/         # Agent 知识库
└── capabilities.db    # DuckDB 数据库
```

## 开发建议

### 添加新的网络设备
1. 编辑 `.olav/config/nornir/hosts.yaml` 添加设备
2. 验证 IP 和凭据在 `.env` 中配置
3. 运行 test_list_devices 验证

### 扩展命令白名单
1. 编辑 `.olav/imports/commands/cisco_ios.txt`
2. 添加新的允许命令（每行一个）
3. 重新运行 test_command_whitelist_enforcement

### 自定义 Agent 行为
1. 编辑 `.olav/OLAV.md` System Prompt
2. 更新 Skills 和 Knowledge 文件
3. 重新运行测试验证效果

## 性能基准

```
Phase 1 MVP 性能指标:

Agent 初始化: ~1s
首次 LLM 调用: ~10-15s (包括网络延迟)
后续 LLM 调用: ~3-5s
设备命令执行: ~2-5s (取决于设备响应)
总测试套件: ~73s (5 个测试)
```

## 下一步

### Phase 2: 完整 Skills
- 扩展快速查询模式
- 实现深度分析框架
- 添加设备巡检

### Phase 3: Subagents
- 配置专业化子代理
- 实现代理委派逻辑

### Phase 4: 自学习
- 自动学习新别名
- 自动保存成功案例

## 相关文档

- [PHASE_1_COMPLETION_REPORT.md](PHASE_1_COMPLETION_REPORT.md) - 详细完成报告
- [DESIGN_V0.8.md](DESIGN_V0.8.md) - 架构设计文档
- [CONFIG_AUTHORITY.md](CONFIG_AUTHORITY.md) - 配置权威指南
- [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) - 架构审视

## 支持

如有问题，请：
1. 检查 [PHASE_1_COMPLETION_REPORT.md](PHASE_1_COMPLETION_REPORT.md) 的故障排除部分
2. 运行 `uv run pytest tests/e2e/test_phase1_mvp.py -v` 进行诊断
3. 查看 test 输出中的详细错误信息
