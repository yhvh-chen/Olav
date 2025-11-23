# 巡检模式（Inspection Mode）- 设计草案（文档）

> 本文仅定义需求、交互与输出格式，暂不包含代码实现。

---

## 目标
- 基于 YAML 模板声明巡检项目，自动分解为 TODO 并执行，生成 Markdown 报告。
- 适用于“每天巡检/每周审计/专项核查”等可重复任务。
- 可通过设置开关启用/禁用；不影响核心 Workflows 默认行为。
- 支持容器内 cron（无须依赖宿主机计划任务）。

## 配置与放置位置
在设置层新增以下字段（文档阶段占位）：

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `INSPECTION_MODE_ENABLED` | bool | `false` | 是否启用巡检模式（关闭则忽略所有相关 CLI 参数） |
| `INSPECTION_CONFIG_DIR` | str | `config/prompts/inspection` | 巡检 YAML 模板目录 |
| `INSPECTION_REPORT_DIR` | str | `reports/inspection` | 输出报告目录 |
| `INSPECTION_DEFAULT_PLAN` | str | `daily_core_checks.yaml` | 默认自动运行的计划文件名 |
| `INSPECTION_MAX_PARALLEL` | int | `5` | 并行执行的最大独立检查数量 |
| `INSPECTION_FAIL_FAST` | bool | `true` | 失败是否立即标记并继续后续检查（false 可重试） |

YAML 模板位置：`config/prompts/inspection/*.yaml`
报告路径：`reports/inspection/{plan_name}-{YYYY-MM-DD}.md`
默认模板（示例）: `config/prompts/inspection/daily_core_checks.yaml`

环境变量示例（.env）：
```env
INSPECTION_MODE_ENABLED=true
INSPECTION_CONFIG_DIR=config/prompts/inspection
INSPECTION_REPORT_DIR=reports/inspection
INSPECTION_DEFAULT_PLAN=daily_core_checks.yaml
INSPECTION_MAX_PARALLEL=5
INSPECTION_FAIL_FAST=true
```

## YAML 模板规范（草案）
```yaml
_type: inspection_plan               # 固定标识
name: daily_core_checks              # 计划名称
schedule_hint: daily 08:00           # 可选，提示性字段

# 目标选择器：建议与 NetBox/SuzieQ 选择器一致
targets:
  namespace: production
  tags: ["core", "olav-managed"]
  # devices: ["R1", "R2"]          # 可选：显式设备列表

# 检查项列表
checks:
  - id: interfaces_down
    title: 接口异常（down/admin-down）
    type: suzieq_query               # suzieq_query / netconf_check / netbox_query ...
    table: interfaces
    method: summarize                # get / summarize / unique / aver
    filters:
      state: ["down", "adminDown"]
    assert:
      mode: must_be_empty            # must_be_empty / ratio_over_total / equals_snapshot
    severity: high                   # high / medium / low
    remediation: 请检查链路/光模块/邻接设备状态

  - id: bgp_session_health
    title: BGP 会话健康
    type: suzieq_query
    table: bgp
    method: summarize
    filters:
      state: ["Established"]
    assert:
      mode: ratio_over_total
      threshold: 0.98
    severity: high
    remediation: 低于阈值时检查告警与邻居状态

  - id: netconf_diff
    title: 关键设备配置漂移
    type: netconf_check              # 运行期可选择性支持（涉及 HITL）
    xpaths:
      - /interfaces/interface[name=xe-0/0/0]/config
    assert:
      mode: equals_snapshot
      snapshot_ref: baseline-2025-11-01
    severity: medium
```

## 执行流程（设想）
1. 读取与校验 YAML（字段存在性 / 合法性）
2. 解析为 TODO 列表（独立项可标记为可并行）
3. 逐项执行（SuzieQ/NetBox/NETCONF 等），使用 Schema-Aware Evaluator 做基础评估：
   - 数据存在性 / 工具状态检查
   - 字段与任务语义相关性
4. 汇总结果并生成 Markdown 报告：
   - 总览统计（通过/失败/不确定）与合规分
   - 明细列表（结论、证据、建议）
   - 附录（必要时包含简要原始数据表）

## 报告结构（Markdown）
```markdown
# 每日巡检报告 - {plan_name} - {YYYY-MM-DD}

## 概览
- 通过: X
- 失败: Y
- 不确定: Z
- 合规评分: 95/100

## 明细
### 1. 接口异常（interfaces_down）
- 结果: 通过 | 失败 | 不确定
- 证据: 表/字段/样例行（必要时）
- 建议: Remediation 文本

### 2. BGP 会话健康（bgp_session_health）
- 结果: 失败（通过率 96% < 98% 阈值）
- 证据: 统计分布 / 关键设备列表
- 建议: 检查邻居 flapping 与告警

...

## 附录（可选）
- 表格/JSON 片段
- 生成时间与数据源说明
```

## CLI（草案，仅文档）
```bash
# 交互式运行
uv run olav.py --mode inspection --plan config/prompts/inspection/daily_core_checks.yaml

# 指定输出文件（非交互）
uv run olav.py --mode inspection \
  --plan config/prompts/inspection/daily_core_checks.yaml \
  --output reports/inspection/daily_core_checks-$(date +%F).md
```

## 容器化定时运行（优先方案）

推荐使用单独的轻量容器服务，通过内置 cron 实现每日自动巡检，避免宿主机任务差异。

### Dockerfile（示例）
```Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install uv && uv sync --no-dev
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# 写入 cron 任务：每天 08:00 执行默认巡检计划
RUN echo "0 8 * * * cd /app && INSPECTION_MODE_ENABLED=true INSPECTION_DEFAULT_PLAN=daily_core_checks.yaml uv run olav.py --mode inspection --plan config/prompts/inspection/${INSPECTION_DEFAULT_PLAN:-daily_core_checks.yaml} --output reports/inspection/daily_core_checks-$(date +\%F).md >> logs/inspection.log 2>&1" > /etc/cron.d/olav-inspection \
    && chmod 0644 /etc/cron.d/olav-inspection \
    && crontab /etc/cron.d/olav-inspection

CMD ["bash", "-c", "mkdir -p reports/inspection logs; cron -f"]
```

### docker-compose 服务（示例）
```yaml
services:
  olav-inspection:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      INSPECTION_MODE_ENABLED: "true"
      INSPECTION_CONFIG_DIR: "config/prompts/inspection"
      INSPECTION_REPORT_DIR: "reports/inspection"
      INSPECTION_DEFAULT_PLAN: "daily_core_checks.yaml"
      INSPECTION_MAX_PARALLEL: 5
    volumes:
      - ./reports/inspection:/app/reports/inspection
      - ./config/prompts/inspection:/app/config/prompts/inspection:ro
    restart: unless-stopped
    profiles: [inspection]
```

### 日志查看
```bash
docker compose --profile inspection logs -f olav-inspection
```

## 宿主机定时（备选方案，仅文档）

### Windows 计划任务（PowerShell）
```powershell
$workDir = "C:\\Users\\<you>\\Documents\\code\\Olav"
$plan    = "config\\prompts\\inspection\\daily_core_checks.yaml"
$outDir  = "reports\\inspection"
$cmd     = "powershell -NoProfile -ExecutionPolicy Bypass -Command \"cd $workDir; if(!(Test-Path $outDir)){New-Item -ItemType Directory -Path $outDir | Out-Null}; uv run olav.py --mode inspection --plan $plan --output $outDir\\daily_core_checks-$(Get-Date -Format yyyy-MM-dd).md\""
schtasks /Create /SC DAILY /ST 08:00 /TN "OLAV Daily Inspection" /TR "$cmd"
```

### Linux/macOS（cron）
```cron
0 8 * * * cd /opt/olav && uv run olav.py --mode inspection --plan config/prompts/inspection/daily_core_checks.yaml --output reports/inspection/daily_core_checks-$(date +\%F).md >> logs/inspection.log 2>&1
```

## 验收标准
- 能从 YAML 成功解析出 N 项检查，逐项执行并生成统一格式的 Markdown 报告。
- 报告包含：统计总览、逐项结论、建议、关键证据。
- 失败/不确定项高亮，附带下一步建议（可选进入 HITL）。

## 开放问题（更新）
- `netconf_check` 等需要 HITL 的操作如何在计划任务中安全运行（是否提供 `--noninteractive` 降级）？
- 是否需要额外输出 JSON 以便自动化平台消费？
- 阈值/基线快照如何管理（导入导出/版本化）？
- 是否需要容器健康检查端点保证 cron 成功执行？
- 报告失败重试策略是否需要（例如：重试 1 次）？
