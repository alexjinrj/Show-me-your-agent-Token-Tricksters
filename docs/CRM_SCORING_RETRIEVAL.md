> 后续补充：现已增加按天异常调查与可配置的网页搜索接口，见 [订单异常调查配置](ORDER_SPIKE_INVESTIGATION.md)。以下为评分与第一阶段检索设计，历史状态重建仍未实现。

# CRM 评分与 Agent 字段检索（2026-09-21）

CRM 的“诊断 → 参数干预 → 模拟 → 比较”验收流程见
[CRM_DIAGNOSIS_SIMULATION_CASE.md](CRM_DIAGNOSIS_SIMULATION_CASE.md)。

本改动基于 main 的 87e8cff，开发分支 `feature/crm-scoring-retrieval`。
本地实现，不表示 GitHub 主分支或 AWS 已更新。未引入新依赖或数据库迁移。

## 1. 为什么改评分

参考公开产品方法，不声称复刻其他公司的专有公式：

- [Klaviyo RFM](https://help.klaviyo.com/hc/en-us/articles/17797889315355)：结合最近购买、频率和金额进行客户分层；其产品有历史长度和客户数量等数据要求。
- [IBM RFM Binning](https://www.ibm.com/docs/en/spss-statistics/31.0.0?topic=analysis-rfm-binning)：相同观测值应有一致的分数，避免随机拆散并列值。

我们采用上述思路，但本项目的 365 天窗口、三项等权、A/B/C 阈值以及优先级参数均为**原型政策**，不是这些公司已验证的参数。当前快照并不能证明有完整一年交易历史，不满足生产级客户价值预测要求。

### 客户价值：RFM

- 基准时间：快照 `as_of`，不使用电脑今天的日期。
- 合格订单：订单日期在 `[as_of - 365 days, as_of]` 内，排除 cancelled/canceled。
- R：距离窗口内最后一次下单的天数，越小越好。
- F：窗口内订单数，越大越好。
- M：窗口内订单金额合计，越大越好。**没有支付证据，因此不称实际消费额、收入或 CLV。**
- 三项都在同一个“窗口内有订单的客户”群体中独立排名。
- F/M 分数：`100 × (小于当前值的人数 + 0.5 × 等于当前值的人数) / 群体人数`。
- R 分数：`100 - 上述排名分数`。
- 总分：三项分数（各保留两位小数）的平均值取整。所有客户值相同时得到 50，单人群体也为 50。
- 分层：A ≥75；B ≥50；其余有窗口订单的为 C。已有订单但窗口内无合格订单为 Inactive；完全无订单为 Prospect。

策略文件 `src/tools/crm/scoring.py`；可在 `CRMService(snapshot, ScoringPolicy(...))` 调整窗口和阈值。默认等权有意作为可解释基线；后续需按业务目标回测，而非凭感觉赋予某一项更高权重。

### 履约异常比例与服务优先级分开

旧“关系风险”按异常件数累加，容易惩罚业务量大的客户。现在兼容旧 API 字段 `riskScore`，但含义明确为：

`100 × 当前派生服务异常订单数 / 当前 open 或 backlog 订单数`

例如 1/2 和 5/10 都为 50%。无待处理订单时兼容值为 0，同时 `riskEvidenceAvailable=false`，不能解释成“已证明不会流失”。High ≥65、Medium ≥35 的旧显示阈值保留，仅用于原型分层。

它不是客户流失概率、信用评分或客诉率。少于 5 个订单会显示小样本提示；5 是提示阈值，不代表达到 5 就有统计可靠性。

服务工单优先级单独按逾期程度：`min(100, round(35 + 逾期天数 × 5))`，不再重复叠加客户异常比例。原型 Critical ≥70、High ≥50；这不是企业 SLA。没有真实投诉严重性/响应记录，不能模拟这些字段。

前端 CRM 案例详情展示 R/F/M、窗口、群体人数、订单样本和政策版本。旧 API 字段保留，新增 `scoreDetails` 与 `priorityPolicy`。

## 2. Agent 如何检索和分析

```text
用户问题
  → LLM 调用 get_data_catalog 了解字段和日期范围
  → LLM 选择字段、筛选条件及分组
  → query_snapshot_records 返回记录、全部匹配记录的汇总与来源
  → compare_snapshot_periods 确定性计算两个期间的差异
  → LLM 解释证据、可能原因及缺失信息
  → 如需测试业务调整，走原有 baseline/alternative simulation
```

这是“LLM 选择工具参数 → 工具读取数据和计算 → LLM 解释”的循环，不让模型自行编 SQL 或计算权威金额。

四个注册入口（共享 Runtime 与 MCP）：

| 工具 | 用途 |
|---|---|
| get_data_catalog | 发现数据集、字段类型、已观测日期范围、数据限制 |
| query_snapshot_records | 筛选、字段选择、最多两字段分组、分页、全量匹配汇总 |
| compare_snapshot_periods | 同一查询下两个不重叠期间的总量、差额、百分比、每日记录数 |
| query_enterprise_history | 预留历史状态接口，明确返回 NOT_IMPLEMENTED |

数据集：orders、customers、cases、inventory。所有数据来自该次 Runtime 使用的同一不可变快照。库存按 SKU 汇总；没有增加仓库级或任意跨表连接。订单已经带 customer_id / sku，其他详情可使用现有工具继续查。

筛选为 AND；eq/in 可用于所有字段，gte/lt 仅限数值及日期。最多 8 条筛选、每页 100 条、最多 100 个分组。分组超过上限返回 `groups_truncated=true`，可以缩小筛选范围再查。合计始终在分页之前计算，不会把第一页误当总数。数值用 Decimal。

日期按 UTC 比较，date-only 是 UTC 零点，期间左闭右开。日期覆盖只是观测记录范围，不能证明区间完整。窗口长度不同需看返回的 period_days / rows_per_day；它们也不是完整历史的真实日均业务量。基准值为 0 时百分比返回 null，而非无限大。

示例参数：

```json
{
  "dataset": "orders",
  "filters": [
    {"field": "order_date", "op": "gte", "value": "2026-08-01"},
    {"field": "order_date", "op": "lt", "value": "2026-09-01"}
  ],
  "fields": ["id", "sku", "amount", "order_date"],
  "group_by": ["sku"],
  "limit": 10
}
```

时间字段查询的是**当前快照内记录的日期**。它无法回答“六月某日仓库当时有多少库存”。历史状态接口不以最新状态代替历史，也不以空列表假装已查到历史。

## 3. 怎么运行和使用

在本仓库根目录按 README 启动：

```bash
uv sync --locked --all-groups
uv run uvicorn interfaces.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

进入 CRM 查看案例评分明细；进入 AI Business Coordinator 输入：

> 先查看可用数据字段和日期范围，然后按月汇总订单数量和金额。选两个有数据的月份比较，进一步按 SKU 分组，说明变化集中在哪里。引用工具证据，区分已知事实、可能原因和缺失数据。

或：

> 查客户 AW00011308，解释 RFM 分数和样本量，再检索他的订单状态。这个异常比例是否足以说明他会流失？

AI 对话仍使用原有 OpenClaw 网关配置 `BC_OPENCLAW_URL` / `BC_OPENCLAW_TOKEN` / `BC_OPENCLAW_AGENT_ID`。本次不用新 API Key、不更换模型；不能把密钥写进前端或 Git。网关未配置时，不能完成真实自然语言调用；CRM 的确定性功能仍可用。

## 4. 验证与尚未完成部分

新增自动测试覆盖并列评分、时间窗口、手算金额、业务规模不同但异常比例相同、分页汇总、未知字段和任意 SQL 拒绝、日期边界、零基准、历史接口明确报错，以及多轮 Runtime 工具调用与证据持久化。

```bash
uv run pytest -q
uv run ruff check src tests scripts migrations
uv run mypy src
node --test tests/frontend/*.test.cjs
```

新增 `test_retrieval_chain.py` 使用**脚本化模型替身**验证工具链，不代表已完成真实 Bedrock 行为评估。真实模型仍需在已配置网关的环境验收：目录 → 查询 → 比较 → 引用结论；不得把无数据月份回答成业务为零。

不含历史状态重建、已证实的活动归因、真实流失预测、团队 data-alignment 分支合并。网页搜索入口见上方后续文档。用户举的“六月是不是促销导致增长”，目前可以调查记录分布，但没有促销标记和外部证据时必须保留为待验证假设。

评分后续评估：补齐足够订单/支付/退款/真实投诉历史；使用时间切分，比较各分层后续复购和服务结果；检查稀疏群体及不同行业表现，再校准窗口和阈值。当前只验证公式正确与可解释，不能宣称预测效果科学可靠。

## 5. 本地快照实测（不是企业总体数据）

2026-09-21 检查本版本随附数据：486 客户、500 笔订单。订单时间为
2026-08-27 16:00 UTC 至 2026-09-11 16:00 UTC，约 16 天，并无六月订单。
全部 486 个客户的窗口内订单数都小于 5。

按 UTC 月份分组：

| 月份 | 快照内订单数 | 订单金额 SGD |
|---|---:|---:|
| 2026-08 | 162 | 3331.33 |
| 2026-09 | 338 | 7131.20 |

这两行是不同长度、不完整月份的快照记录，不能称为完整的月销售额增长。
新分层为 A 20、B 227、C 239。示例 AW00011308 仅一笔订单：
R=15.74、F=48.87、M=0.51，总分22，C；待处理异常比例1/1=100%，
小样本提示开启。100%描述唯一待处理订单的状态，不表示客户必然流失。

本次最终验证：在本分支独立 `.venv` 中按 `uv.lock` 安装；Python 测试 **136 passed**；前端测试 **3 passed**；Ruff、Mypy（72 个源文件）、`git diff --check` 通过；全新临时数据库启动及各业务模块 smoke 检查通过。测试存在依赖弃用提醒，无失败。未调用真实收费模型，未推送 GitHub 或部署 AWS。
