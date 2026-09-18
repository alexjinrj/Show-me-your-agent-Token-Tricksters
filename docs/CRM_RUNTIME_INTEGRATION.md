# CRM 统一数据接入与 Runtime 交接

## 当前数据方案

CRM 不再加载 Olist，直接使用 `DemoContext` 提供的不可变 AdventureWorks
`SnapshotBundle`，与 Sales/Inventory 共用相同的快照 ID、客户号、订单号、SKU 和 SGD 币种。
不新增一份客户/订单数据库，不重新读取 CSV 作为旁路，也不依赖浏览器本地数据。

现有统一演示快照包含 486 个客户、500 个销售订单和 40 个 SKU。
CRM 将 100 个 backlog 订单投影为 `CASE-SO...` 订单服务异常案件；
例如 `CASE-SO74695` 来源于 `SO74695`，客户号为 `AW00011308`。
这些是派生案件，不是客户实际提交的投诉。未来源数据改变时，数量以工具查询为准。

`BC_CRM_DATA_PATH` 配置入口已移除；旧 Olist 夹具不参与运行，无需上传或部署。
队员代码来源为 `main@ac9d327:repo-overlay/`，经过改造后接入正式目录，
统一数据版完整链路来自 `feature/agent-runtime`，此整合版本同时接入绿色分模块前端。

## 完整链路

```text
统一 Enterprise State -> 不可变 SnapshotBundle
                       -> Sales / Inventory / CRMService
                       -> 共享 ToolRegistry / ToolExecutor
                       -> OpenClaw Gateway 函数调用 -> 证据 / 审计 / AgentRun -> 前端

CRM 建议 / 未发送草稿 -> 人工提交提案（关联 AgentRun / 工具证据）
                     -> SQL crm_proposals -> 人工批准 / 拒绝 -> 重启后读取
```

统一 Registry 包含 11 个 Sales、2 个 Inventory、10 个只读 CRM 工具。
Web 与独立 MCP 入口共用执行器；Web 路径不另外运行 CRM 模型，也不绕过本地证据/作用域校验。

## 数据与计算边界

- 客户身份沿用快照的 `customer_number`，如 `AW00011308`。
- 客户价值基于订单金额与订单次数；不能当作已支付消费或信用评分。
- 服务案件由 backlog 或逾期且未完成的订单派生。已 shipped/paid 的订单不进入待履约异常队列。
- 逾期依据订单 `due_date` 和快照 as-of 时间，不是投诉 SLA。
- 库存直接读取同一快照的 SKU/仓库数量；`pendingOrderUnits` 是全部 pending 订单义务，
  不是仓库实际预留。`availableUnits` 扣除全部义务；
  `availableForThisOrder` 扣除其他订单义务，用于当前订单的履约评估。
- 金额使用后端 Decimal 与 SGD，直接读取订单金额、商品标准成本和订单数量。
  退款敞口仅为条件性估计；商品标准成本不是已入账退款、费用或利润。
- 真实投诉、评论、首次响应、投诉 SLA、确认交付时间、支付/退款资格、补偿政策、
  物流费和解决 ETA 尚无源数据，返回不可用或空值，不补造模拟记录。
- 服务补偿 credit 方案因政策缺失不可提交；退款方案只是“核查取消/退款资格”的审核建议。
- `provenance` 保留快照指纹、公司、原始行 lineage 及上游 source/derived/synthetic 来源。
  CRM 自身不新增随机库存、SLA 回放或补偿百分比假设。

工具 `reference_id`、API `dataset_reference` 与 Runtime `snapshot_id` 一致。
`state_type=actual` 表示规范快照读取；派生评分和案件通过
`caseKind=derived_order_service_exception`、`data_scope` 和 `provenance` 单独标明。

## API 与工具

`/api/v1/crm/*` 返回 `crm-api-v1`、`dataset_reference`、`data`、`provenance`：

- `GET /provenance`、`GET /summary`
- `GET /customers`、`GET /customers/{customer_id}`
- `GET /complaints?limit=24`、`GET /complaints/{complaint_id}`
- `GET|POST /proposals`、`GET /proposals/{proposal_id}`
- `POST /proposals/{proposal_id}/decision`

为兼容队员 UI，`complaints` 路径、`complaint_id` / `complaintId` 参数和部分工具名称保留。
它们现在接收 `CASE-SO...` 服务案件号，不能据名称推断存在真实投诉。
summary 的 `complaintCount`、`unrespondedComplaints` 为空；
展示队列数量用 `serviceCaseCount`，订单逾期数量用 `overdueOrders`。

CRM 工具包含汇总、优先队列、客户 360、案件详情、订单时间线、库存可用量、
条件性财务敞口、方案比较、服务建议与未发送草稿。
旧 `/api/crm/*` 兼容路由仍保留，但同样使用统一快照。

## 人工审核与作用域

聊天证据中的 **Review CRM recommendation** 按钮打开案件表单，并传递
`sourceAgentRunId` / `sourceToolCallId`。两者必须同时提供。
后端验证运行完成、成功的建议工具、案件及快照引用一致，保存提交时调查、来源证据及选定方案。
手动从 CRM 面板提交可以不传 Runtime 来源，但仍保存快照和调查证据。

人工填写审核人后批准或拒绝，原子状态更新禁止重复覆盖最终决定。
非法来源、未知政策或不可行方案返回 422；重复/跨快照审批返回 409。
旧快照或历史 Olist 审核记录保留在数据库，但不混入当前快照列表或当前审核流程。

所有提案与批准只记录人工审核，不发送客户消息，不退款、不发货、不修改 Actual State。
API 无用户鉴权，因此“审核人”是演示输入而非已验证身份；后端与 Gateway 必须保持私有访问。

## 启动与迁移

```bash
uv sync --all-groups
uv run uvicorn interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

已有数据库须先停服务并备份；在与 API 相同的 `BC_DB_PATH` 环境下：

```bash
uv run python scripts/migrate_runtime.py
# 核对目标路径、停服务和备份后才执行：
uv run python scripts/migrate_runtime.py --apply
```

迁移包含 `0005_crm_proposals` 和 `0006_crm_runtime_evidence`，不删除历史记录。
缺少 Gateway URL/Token 时自然语言分析 disabled，但 CRM 读取和人工审核 API 仍可用。
真实 Lightsail 模型验收见 [接入说明](AWS_LIGHTSAIL_OPENCLAW_接入说明.md)。

## 验证

```bash
uv run pytest tests/unit/test_crm_tools.py tests/api/test_crm.py tests/api/test_crm_runtime_chain.py tests/integration/test_openclaw_mcp.py -q
uv run ruff check src tests scripts migrations
uv run mypy src
node --test tests/frontend/assistant.test.cjs
uv run python scripts/smoke_agent_runtime.py
```

自动化 Gateway 测试使用模拟 HTTP 服务，实际调用业务工具、数据库与 MCP。
统一数据版本全量 Python 回归通过 121 项，前端通过 3 项，Ruff/mypy/JS 语法检查通过。
本地默认数据库已备份后迁移至 0006；实际启动读取通过，Actual State 哈希保持一致。
它验证统一快照/客户/金额/库存一致性及审核证据闭环，不替代真实 OpenClaw 模型验收。
smoke 测试需要配置并运行 API，会执行真实模型请求；只分析并保存模拟/审计，不自动提交或审批提案。
