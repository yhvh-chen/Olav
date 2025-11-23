# IMPLEMENT_PLAN

> 文档阶段：规划 Inspection Mode 与普通模式轻量反思能力的实施步骤。无代码变更，仅路线图。

## 概述
本计划覆盖两项新能力：
1. 普通模式轻量反思（Reflection Self-Check）
2. 巡检模式（Inspection Mode）启用/模板/容器化调度

## 里程碑划分
| 阶段 | 内容 | 产出 | 预计时长 |
|------|------|------|---------|
| M1 | 配置层扩展 | Settings 字段、env 支持 | 0.5d |
| M2 | 模板与解析骨架 | YAML Loader + Schema 校验 | 1.0d |
| M3 | 执行器抽象 | Check Runner 接口 + 并行控制 | 1.0d |
| M4 | 报告生成 | Markdown Renderer + 统计聚合 | 0.5d |
| M5 | 容器调度与运维 | Dockerfile + compose profile + cron 集成 | 0.5d |
| M6 | 轻量反思集成 | 普通模式结果自检 + 输出片段 | 0.5d |
| M7 | 测试与验收 | 单元测试 + 示例计划验证 | 0.5d |

## 设置与配置（M1）
新增 Settings 字段（示例）:
```python
class Settings(BaseSettings):
    inspection_mode_enabled: bool = False
    inspection_config_dir: str = "config/prompts/inspection"
    inspection_report_dir: str = "reports/inspection"
    inspection_default_plan: str = "daily_core_checks.yaml"
    inspection_max_parallel: int = 5
    inspection_fail_fast: bool = True
    reflection_self_check_enabled: bool = True
```

## 模板与解析（M2）
- 语法校验：必须字段 `_type`, `name`, `checks`；可选 `targets`、`schedule_hint`。
- Schema 校验：表是否存在 → 字段是否存在 → 断言模式合法性。
- 将每个 `check` 转换为标准内部结构：
```python
{
  "id": str,
  "driver": "suzieq"|"netconf"|"netbox",
  "table": str | None,
  "method": str | None,
  "filters": dict,
  "assert": {"mode": str, ...},
  "severity": "high"|"medium"|"low"
}
```

## 执行器抽象（M3）
接口草案：
```python
class InspectionExecutor(Protocol):
    async def run(self, check: dict) -> dict: ...  # 返回 {status, data, meta}
```
并行控制：
- 根据 `inspection_max_parallel` 分批执行 independent checks。
- 保留执行顺序与时间戳，失败不阻断整体（除非 fail_fast=false）。

## 报告生成（M4）
Renderer 输入：所有检查结果 + 统计聚合。
聚合字段：通过 / 失败 / 不确定 / 合规分（简单权重：high=3, medium=2, low=1）。
输出：Markdown + 可选 JSON（扩展）。

## 容器化调度（M5）
- Dockerfile 增加 cron，定时执行默认计划。
- compose profile `inspection` 独立启动。
- 日志：`logs/inspection.log`；可选健康检查端点。

## 轻量反思集成（M6）
普通模式结束前：
- 收集本次使用的表/字段/工具。
- 运行自检逻辑：字段相关性 + 数据存在性。
- 输出片段：`质量自检`。

## 测试与验收（M7）
- 模板解析单测：非法字段 / 缺少字段 / 正常样例。
- 执行器单测：Mock suzieq_parquet_tool / netconf_tool。
- 报告生成单测：多状态混合。
- 反思片段单测：相关性判定分支覆盖。

## 风险与缓解
| 风险 | 说明 | 缓解 |
|------|------|------|
| 并行执行竞争 | 工具频繁 IO 可能争用 | 限制并行度 + 添加重试 |
| 模板膨胀 | 用户自定义字段过多 | 严格 schema 校验 + 忽略未知字段 |
| cron 时间漂移 | 容器重启后任务延迟 | 可选健康检查 + 手动触发脚本 |
| 反思增加延迟 | 普通模式响应变慢 | 基于结果大小自适应跳过 |

## 初始默认模板
路径：`config/prompts/inspection/daily_core_checks.yaml`
内容：复用文档示例，添加最少三个检查（接口 down、BGP 会话、配置漂移）。

## 验收 Checklist
- [ ] Settings 字段可被环境变量覆盖
- [ ] 默认模板加载成功
- [ ] CLI `--mode inspection` 在启用时可运行，禁用时报错提示
- [ ] 并行执行按最大并发分批
- [ ] 报告包含统计与明细
- [ ] 反思输出片段出现在普通模式结果底部（启用时）
- [ ] 容器每日自动生成报告文件

## 后续扩展（非本阶段）
- JSON 报告输出
- 基线快照管理命令
- 失败重试策略
- 健康检查 HTTP 端点
- 阈值动态学习（Episodic Memory）
