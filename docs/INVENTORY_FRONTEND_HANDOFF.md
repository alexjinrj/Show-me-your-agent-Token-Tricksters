# Inventory 前端补充展示：AI 实施交接说明

> 使用方式：把本文件完整交给负责前端的 AI（Cursor、Codex 等）。它应先检查代码，再按本说明实施。不要只把其中一段当作提示词。

## 1. 任务目标

在现有 **Inventory Management** 页面保留当前库存概览的基础上，补充展示 Inventory 后端已经具备、但当前主页面尚未展示的能力：

1. 可筛选的补货候选项；
2. 四种补货策略的模拟比较；
3. 系统推荐策略及推荐依据；
4. 需求缺口、模拟运行证据和关键指标；
5. 清晰区分 Actual State 与 Simulated State。

这不是重新开发 Inventory 计算逻辑。前端只负责输入、调用结构化接口、展示结果和处理交互状态。

## 2. 必须遵守的边界

- 不修改 `src/tools/sales/`，也不要让 Inventory 与 Sales 共用业务代码。
- 不新增 Inventory 专用 LLM runner。聊天页继续使用现有共享 Runtime；Inventory 主页面使用结构化 REST API。
- 不在 JavaScript 中复制补货规则、风险判断、需求缺口或策略推荐算法。计算结果必须来自后端。
- 不把 `/api/assistant` 的自然语言回答解析成页面数据。
- 不创建采购订单，不修改 Actual State。策略比较是 what-if simulation，但会持久化 simulation run 作为证据。
- 不硬编码演示结果、snapshot ID、run ID 或 SKU。
- 保持现有 Sales、Accounting、Operations、CRM 页面行为不变。

## 3. 当前实现状况

### 3.1 当前 Inventory 页面已经展示

现有页面位于：

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

当前页面调用：

```text
GET /api/v1/modules/inventory
```

当前已经展示：

- Active SKUs
- Warehouses
- On-hand units
- Value at standard cost
- Reorder candidates 数量
- Critical 数量
- Risk distribution
- Reorder candidates 表格：SKU、Item、Stock、Reorder point、Recommended、Risk

这些内容应保留。

### 3.2 后端已有但主页面未展示

后端 Inventory tool surface 已提供两项能力：

```text
list_inventory_reorder_candidates
compare_inventory_replenishment_strategies
```

相关源文件：

- `src/tools/inventory/contracts.py`
- `src/tools/inventory/tools.py`
- `src/tools/inventory/reorder.py`
- `src/tools/inventory/demand.py`
- `src/tools/inventory/strategy.py`
- `src/tools/inventory/recommendation.py`
- `src/agent_runtime/inventory_registry.py`
- `src/interfaces/mcp/server.py`

当前缺少的主要展示内容：

| 能力 | 当前页面 | 目标状态 |
| --- | --- | --- |
| 按风险等级筛选补货候选项 | 未提供控件 | 提供 `all/critical/high/medium/low` 筛选 |
| 控制返回数量 | 未提供控件 | 提供 `top_n`，范围 1–100 |
| 比较四种补货策略 | 未展示 | 展示 baseline、critical_only、demand_aligned、full |
| 推荐策略 | 未展示 | 单独的推荐摘要并高亮对应策略 |
| 需求缺口 | 未展示 | 展示 SKU 与 shortage quantity |
| 模拟关键指标 | 未展示 | 展示四种策略的对比表 |
| Simulation run 证据 | 未展示 | 展示可复制的 run ID 和 result hash |
| 假设与限制 | 未展示 | 展示 recommendation 中的 assumptions、limitations |
| CSV 导出脚本 | 只有 CLI | 作为后续增强，不能由浏览器直接运行脚本 |
| Tool audit | 后端内部存在 | 不放在普通 Inventory 页面；如需要应做独立 Admin/Audit 页面 |

## 4. 开始编码前必须检查的接口问题

目前 `src/interfaces/api/routes_modules.py` 只暴露了概览接口：

```text
GET /api/v1/modules/inventory
```

Runtime/MCP tool 并不等于浏览器可以直接调用的 REST API。开始前请检查当前分支是否已经增加以下等价接口。如果没有，先向负责人说明：**前端策略页面存在结构化 API 依赖**。

建议的最小 REST 设计如下；路径名称可以根据项目现有规范调整，但返回字段必须保持结构化和稳定。

### 4.1 补货候选项接口

```http
GET /api/v1/modules/inventory/reorder-candidates?risk_level=all&top_n=10
```

服务端应使用当前 `DemoContext.base_snapshot_id`，不要要求浏览器硬编码 snapshot ID。服务端调用 `InventoryAgentTools.call()` 时可使用固定、可审计且不超过 80 字符的 `agent_case_id`，例如 `inventory-dashboard`。

预期业务数据：

```json
{
  "snapshot_id": "uuid",
  "snapshot_hash": "hash",
  "state_type": "actual",
  "candidate_count": 3,
  "total_recommended_quantity": "120",
  "candidates": [
    {
      "sku": "SKU-001",
      "name": "Item name",
      "current_stock": "10",
      "reorder_point": "20",
      "target_stock": "40",
      "needs_reorder": true,
      "risk_level": "medium",
      "recommended_quantity": "30"
    }
  ]
}
```

### 4.2 策略比较接口

```http
POST /api/v1/modules/inventory/strategy-comparison
Content-Type: application/json
```

请求：

```json
{
  "horizon_days": 30,
  "random_seed": 42,
  "effective_day": "3"
}
```

约束：

- `horizon_days`: 1–365，默认 30；
- `random_seed`: integer，默认 42；
- `effective_day`: 大于等于 0，默认 3；
- snapshot ID 由服务端从当前 DemoContext 获取。

服务端应复用 `compare_inventory_replenishment_strategies`，不要在 route 中重新实现策略算法。该操作会保存四个 simulation runs，因此必须使用 `POST`，不能伪装成纯读取的 `GET`。

工具的最外层可能是通用 `ToolResponse`：

```json
{
  "tool_call_id": "uuid",
  "tool_name": "compare_inventory_replenishment_strategies",
  "status": "ok",
  "state_type": "simulated",
  "reference_id": "recommended-run-id",
  "data": {}
}
```

如果 REST route 继续保留该 envelope，前端必须检查 `status` 后读取 `data`；如果 route 解包为模块统一 envelope，应在 API 测试中固定最终契约。不要让前端同时猜测两种结构。

## 5. Inventory 页面目标结构

在现有 Inventory panel 下方增加 **Replenishment Strategy Analysis** 区域。

### A. Actual inventory / Reorder candidates

保留现有 KPI、风险分布和候选表，并增加：

- Risk level 下拉框：All、Critical、High、Medium、Low；
- Result limit：默认 10，允许 1–100；
- Refresh candidates 按钮；
- 结果摘要：candidate count、total recommended quantity；
- 表格增加 Target stock 列；
- 区域标签明确写 `Actual snapshot`。

筛选只改变候选项结果，不应修改库存。

### B. Strategy controls

增加三个输入和一个操作按钮：

- Horizon days，默认 30；
- Effective replenishment day，默认 3；
- Random seed，默认 42；
- `Compare strategies` 按钮。

按钮行为：

- 请求中禁用按钮并显示明确 loading 状态；
- 防止双击产生重复 simulation runs；
- 成功后展示结果；
- 失败时在该区域内显示可读错误，不要使用静默失败；
- 参数改变后，旧结果应标记为 stale 或清空，不能让用户误以为结果对应新参数。

### C. Recommended strategy

结果顶部展示推荐摘要：

- `recommended_strategy`
- `selection_method`
- `replenishment_quantity`
- `backlog_reduction`
- `fulfilment_improvement`
- `gross_profit_improvement`
- `cash_improvement`
- `actual_state_unchanged`

要求：

- 用人类可读名称展示策略，例如 `critical_only` → `Critical only`；
- 推荐的策略行在比较表中高亮；
- `actual_state_unchanged` 必须以显眼但不夸张的说明展示，例如：`Simulation only — actual inventory was not changed.`；
- 不要把推荐描述为自动执行的采购决定。

### D. Four-strategy comparison

必须展示四行：

1. `baseline`：不增加补货事件；
2. `critical_only`：只处理 critical reorder candidates；
3. `demand_aligned`：按 active demand 的 shortage 补货；
4. `full`：处理所有需要补货的候选项。

主比较表建议字段：

| 返回字段 | 页面名称 | 格式 |
| --- | --- | --- |
| `strategy` | Strategy | humanize |
| `event_count` | Events | integer |
| `replenishment_quantity` | Replenishment qty | number |
| `metrics.ending_backlog` | Ending backlog | integer，越低越好 |
| `metrics.fulfilment_rate` | Fulfilment rate | percentage |
| `metrics.stockout_count` | Stockouts | integer，越低越好 |
| `metrics.ending_inventory_quantity` | Ending inventory | number |
| `metrics.ending_inventory_value` | Ending inventory value | SGD |
| `metrics.gross_profit` | Gross profit | SGD |
| `metrics.ending_cash` | Ending cash | SGD |
| `metrics.minimum_cash` | Minimum cash | SGD |
| `simulation_run_id` | Run ID | monospace、可复制 |

其余指标放在每行的 details/expand 区域，不能丢失：

- `average_waiting_hours`
- `resource_utilization`
- `revenue`
- `cost_of_goods_sold`
- `accounts_receivable`
- `accounts_payable`
- `result_hash`

注意：后端通过 canonical serialization 返回的 Decimal 很可能是字符串。显示时可以转换用于格式化，但不要改写原始响应或因空字符串产生 `NaN`。

### E. Demand shortages

展示 `demand_shortages`：

| 字段 | 页面名称 |
| --- | --- |
| object key | SKU |
| object value | Shortage quantity |

如果为空，展示：`No demand shortage was found for the current snapshot.`，不要留下空白区域。

### F. Assumptions, limitations and evidence

在结果下方增加可展开区域：

- Assumptions：来自 `recommendation.assumptions`；
- Limitations：来自 `recommendation.limitations`；
- Snapshot ID 与 snapshot hash；
- Baseline run ID；
- Recommended run ID；
- 每个 strategy 的 simulation run ID 与 result hash。

这些字段是可审计证据，不应只显示 tooltip；至少要能展开查看和复制。

## 6. 建议的前端实现方式

优先复用 `frontend/app.js` 中已有工具：

- `api()`
- `renderModuleStats()`
- `renderTable()`
- `formatNumber()`
- `formatSgd()`
- `formatPercent()`
- `humanize()`

可以新增小型、Inventory 专用的渲染函数，例如：

```text
loadInventoryCandidates()
runInventoryStrategyComparison()
renderInventoryRecommendation()
renderInventoryStrategyRuns()
renderInventoryShortages()
renderInventoryEvidence()
```

不要把所有逻辑继续塞进现有 `renderInventory()`。`renderInventory()` 负责初始概览，新函数负责交互式候选项和策略结果。

HTML 建议使用语义化结构：`form`、`label`、`button`、`table`、`details/summary`。所有输入必须有 label，loading/error 文本应可被屏幕阅读器感知；不要只依赖颜色区分 recommended、critical 或 error。

样式应沿用现有设计 token、panel、table 和 badge 风格。不要为 Inventory 引入新的 UI 框架。

## 7. 加载、错误与空状态

至少处理以下情况：

- 页面初始概览加载失败；
- 候选项接口返回空数组；
- strategy comparison 正在运行；
- API 返回 validation error；
- API 返回 `status: error`；
- 网络/服务器异常；
- `demand_shortages` 为空；
- 某个可选指标为空；
- 用户连续点击 Compare；
- 旧请求晚于新请求返回，不能覆盖新结果。

推荐为交互请求使用 `AbortController` 或 request sequence ID，避免竞态覆盖。

## 8. CSV 与 Audit 的处理

### CSV

`scripts/reorder_inventory.py` 是 CLI 入口，不是浏览器接口。第一阶段不要从前端尝试运行本地脚本。

如果产品要求页面下载 CSV，应另加后端 download endpoint，由后端复用 Inventory 逻辑生成文件。前端只提供 `Download CSV` 按钮。该项可以作为 P2，不应阻塞策略展示。

### Audit

Inventory tool calls 已在后端审计。普通 Inventory 页面不需要显示完整 audit trail，因为其中可能包含运行细节。若确实要展示，应作为独立、受权限控制的 Admin/Audit 功能，不要混进本次普通用户页面。

## 9. 推荐实施顺序

1. 检查是否已有结构化 REST endpoints；没有则先确认并补最小 API adapter。
2. 为 endpoints 添加 API 测试，固定请求、返回 envelope 和错误格式。
3. 增加 Inventory strategy HTML 容器和表单。
4. 增加候选项筛选交互。
5. 增加 strategy comparison 请求及推荐摘要。
6. 增加四策略比较、shortages、assumptions、limitations、evidence。
7. 完成 loading、error、empty、stale 和竞态处理。
8. 做响应式与可访问性检查。
9. 运行全套静态检查和测试。

## 10. 验收标准

- [ ] 原有 Inventory KPIs、风险分布和候选表仍正常展示。
- [ ] 用户可按 risk level 和 top_n 刷新候选项。
- [ ] 页面明确标识候选项来自 Actual snapshot。
- [ ] 用户可设置 horizon days、effective day、random seed。
- [ ] 点击 Compare 后恰好展示四种策略。
- [ ] 推荐策略与后端 `recommended_strategy` 一致，并在表格高亮。
- [ ] demand shortages 有数据时展示列表，无数据时展示明确空状态。
- [ ] 关键 simulation metrics、run IDs、result hashes 可查看。
- [ ] assumptions 与 limitations 可查看。
- [ ] 页面明确说明 simulation 没有修改 Actual State。
- [ ] validation、tool error、network error 都有可读反馈。
- [ ] 请求期间按钮禁用，重复点击不会产生重复 run。
- [ ] 前端没有复制 Python 中的补货/推荐算法。
- [ ] 没有修改 `src/tools/sales/`。
- [ ] 没有新增 Inventory LLM runner。
- [ ] 其他业务页面无回归。

## 11. 完成后需要回报的内容

负责实现的 AI 完成后，请提供：

1. 修改和新增的文件清单；
2. 最终 REST API 契约；
3. 页面新增区域说明；
4. 自动化测试结果；
5. 仍未实现或需要后端确认的事项；
6. 截图或录屏，至少覆盖默认状态、成功结果和错误状态。

建议验证命令：

```powershell
uv run ruff check .
uv run mypy
uv run pytest -q
git diff --check
git diff -- src/tools/sales
```

最后一条命令应无输出，以证明本次 Inventory 前端补充没有改动 Sales 工具实现。
