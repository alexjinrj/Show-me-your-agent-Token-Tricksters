# Sales Agent LLM 测试用例

这组用例只验收销售板块：销售订单总量、订单状态、积压订单、积压金额、订单级证据、数据时间边界和职责边界。不测试客户关系、库存决策、会计指标或运营资源方案。

先进入项目目录并加载 `.env`：

```bash
cd /home/users/nus/yangyanh/hackthon/Show-me-your-agent-Token-Tricksters-main
set -a; source .env; set +a
```

每个用例使用独立输出目录，避免覆盖轨迹。为节省 token，逐个运行，并保持 `--mode exceptions`。

## 用例 1：销售订单概览

```bash
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py --database sales_demo.db --mode exceptions --max-tool-calls 2 --max-output-tokens 450 --trace-dir sales_report/sales-case-overview --prompt '给出当前销售订单概览：订单总数、各状态数量、积压订单数和积压金额。只报告销售数据，不分析库存、客户画像、财务或仓库资源；180字内回答并引用证据。'
```

验收：应调用 `get_actual_state_summary`；应报告 500 单，其中 `collect_customer_payment` 268、`ship_goods` 132、`allocate_inventory` 100，积压 100 单，积压金额 SGD 482.80；所有数字应标为当前实际快照数据并引用工具或快照 ID。

## 用例 2：销售积压构成

```bash
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py --database sales_demo.db --mode exceptions --max-tool-calls 3 --max-output-tokens 450 --trace-dir sales_report/sales-case-backlog --prompt '只从销售订单角度分析当前积压：积压总数、金额和按SKU的订单数量。不要讨论库存是否充足，也不要推断积压原因；180字内回答并引用证据。'
```

验收：应报告积压 100 单、金额 SGD 482.80；按销售订单 SKU 分布为 TT-M928 55 单、WB-H098 39 单、PK-7098 6 单。不得引用库存量、补货点或把 SKU 分布解释为缺货原因。

## 用例 3：追踪一张销售订单

```bash
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py --database sales_demo.db --mode exceptions --max-tool-calls 3 --max-output-tokens 450 --trace-dir sales_report/sales-case-order-trace --prompt '追踪销售订单 SO74695。告诉我当前订单状态、所在节点和已有事件证据；不要推断缺失的订单历程，180字内回答。'
```

验收：应调用 `trace_business_object`；回答应包含 `backlog`、`allocate_inventory`、已有事件数量，并说明 `history_complete=false` 或等价的历史不完整结论。不得编造订单经历过的其他节点。

## 用例 4：列出积压订单证据

```bash
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py --database sales_demo.db --mode exceptions --max-tool-calls 3 --max-output-tokens 500 --trace-dir sales_report/sales-case-order-evidence --prompt '列出当前销售积压异常，并给出5个代表性销售订单号作为证据。只回答ORDER_BACKLOG，不报告库存异常或运营原因；200字内回答。'
```

验收：应调用 `list_exceptions`；应报告 `ORDER_BACKLOG=100`，并从工具结果引用订单号，例如 SO74695、SO74700、SO74701、SO74703、SO74704。不得把同时返回的库存异常写进最终销售报告。

## 用例 5：销售历史数据边界

```bash
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py --database sales_demo.db --mode exceptions --max-tool-calls 2 --max-output-tokens 350 --trace-dir sales_report/sales-case-history --prompt '过去一周销售积压数量是上升还是下降？必须使用工具核实；数据不存在就说明缺失内容，不要估算，120字内回答。'
```

验收：应调用 `get_metric_history`，查询 `backlog_count` 并得到 `availability=not_available`。Agent 应说明当前只有销售订单状态快照，缺少历史指标序列，不得生成趋势或百分比。

## 用例 6：销售职责边界

```bash
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py --database sales_demo.db --mode exceptions --max-tool-calls 2 --max-output-tokens 350 --trace-dir sales_report/sales-case-scope --prompt '请根据销售数据决定应该补多少库存、调整多少仓库员工，并计算利润和现金流。销售Agent只回答自己能证实的内容，其他部分明确交给对应板块；150字内回答。'
```

验收：Agent 可以引用销售订单积压作为销售侧事实，但不得自行给出库存采购量、仓库人数、利润或现金流结论；应明确这些分别需要存货、运营和会计板块处理。不得调用 SQL 或修改 Actual State。

## 查看与判定

例如用例 3 的文件是：

```text
sales_report/sales-case-order-trace/llm_trace.html
sales_report/sales-case-order-trace/llm_trace.json
```

记录每个用例的 `status`、`finish_reason`、工具名称、参数和 `total_tokens`。只有 `status=complete`、工具轨迹符合预期且最终回答满足职责边界时才算通过。若 `finish_reason=length`，先收紧回答字数，再考虑提高 `--max-output-tokens`。
