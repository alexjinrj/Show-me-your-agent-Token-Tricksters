# 销售 Agent 最新链路与网页验收

基线：`main@2cd72fe`，已包含销售闭环、对象历史回放与库存策略。此工作区增加网页直测入口、结果面板、Skill 路由说明和最小测试集。

## 两条网页路径

| 路径 | 用途 | 是否需要 Gateway |
|---|---|---|
| `POST /api/v1/sales/backlog-analysis` | 固定参数运行真实 Sales Analysis Service；验证仿真与审计 | 否 |
| `POST /api/assistant` | 测试模型是否根据问题动态选择 Tool | 是 |

在 Assistant 页的 **Sales backlog experiment** 输入新增仓库员工数、周期和 seed，点击 **Run matched simulation**。页面显示当前事实、未证实的原因假设、运营干预、baseline/alternative 指标表、总体 verdict 及折叠审计 ID。聊天路径若调用 `analyze_sales_backlog_intervention`，复用同一结果面板。页面验证 Run ID 不同、Snapshot Hash 相同、周期与 seed 匹配、Actual State 未改变；版本或不变量错误时显示合同错误。所有文字使用 `textContent`。

## 业务策略与工具选择

| 用户意图 | 推荐 Tool | 证据边界 |
|---|---|---|
| 当前销售积压 | `get_actual_state_summary`、`list_exceptions`、`trace_process_bottleneck` | 当前快照 |
| 开放式字段查询/排名 | `get_data_catalog` → `query_snapshot_records` | 全匹配聚合；返回页不是总体 |
| 按订单日期比较时段 | `compare_snapshot_periods` | 订单记录日期；不能推断历史状态 |
| 一张订单过去的状态 | `query_enterprise_history` | 只在有可逆事件时重建；可能 unavailable |
| 历史积压/等待时间趋势 | `get_metric_history` | 当前仍为 `not_available` |
| 增加仓库人员是否改善积压 | `analyze_sales_backlog_intervention` | 匹配 baseline/alternative，模拟结果 |

`query_enterprise_history` 已经实现对象级回放，不能把它描述成 `NOT_IMPLEMENTED`；它也不能代替历史积压指标序列。销售 Service 当前依赖不可变 Snapshot，历史 Provider 尚未接入这个特定分析用例。

## 最小测试集

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m pytest tests/api/test_sales_analysis_web.py tests/api/test_react_sales_cases.py tests/integration/test_sales_agent_tools.py tests/unit/test_enterprise_history_retrieval.py -q
node --test tests/frontend/assistant.test.cjs
```

`test_sales_analysis_web.py` 验证 REST 合同、匹配的持久化仿真 Run、审计与 Actual State 不变。`assistant.test.cjs` 验证页面渲染与不变量阻断。`test_react_sales_cases.py` 使用脚本化 Gateway 检查模糊需求下的“发现字段 → 查询记录 → 请求明确干预”，随后在同一 conversation 中选择上层仿真 Tool，并在历史指标缺失时停止。这是 Runtime 协议和编排测试，不能证明真实模型一定会做相同决策。

## 真实 Gateway 手工验收 Prompt

1. `先看看销售有没有问题，再考虑方案。` 预期先查事实/字段，必要时询问想测试什么，不应直接创建仿真。
2. `当前积压如果增加2名仓库员工，7天、seed 42，等待时间如何变化？` 预期关键调用 `analyze_sales_backlog_intervention`，页面展示事实、假设、干预、比较和审计。
3. `过去几周积压是上升还是下降？必须用历史积压指标。` 预期 `get_metric_history` 返回 `not_available`，不得编造趋势。
4. `SO74695 在过去某天是什么状态？` 预期 `query_enterprise_history`，仅按其 `reconstruction_status` 报告，不用当前状态冒充过去状态。

每个真实模型 Case 保存 `agent_run_id`、Tool 顺序与参数、工具结果、最终回答。通过条件是：Tool 路径与意图相符，数字来自证据，模拟不被说成已执行，原因假设不被说成已证实。
