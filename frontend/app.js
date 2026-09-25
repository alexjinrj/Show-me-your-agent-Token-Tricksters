"use strict";

// Business Coordinator demo SPA. Vanilla JS, no build step. All numeric values
// arrive as strings (Decimal) from the API and are displayed verbatim.

const state = {
  sessionId: null,
  conversationId: null,
  chatBusy: false,
  events: [],
  processes: [],
  lastRun: null,
  baselineSessionId: null,
  baselineRunId: null,
  crmComplaintId: null,
  crmComplaint: null,
  crmSource: null,
  inventoryCandidateRequest: 0,
  inventoryStrategyRequest: 0,
  inventoryStrategyBusy: false,
  inventoryStrategyHasResult: false,
  playback: { timer: null, index: 0, trace: [], hours: [] },
};

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

function setStatus(message, isError = false) {
  const status = document.getElementById("status-message");
  status.textContent = message;
  status.classList.toggle("error", isError);
}

async function runAction(message, action) {
  setStatus(message);
  try {
    await action();
    setStatus("");
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ---- Process flows (Task 7) --------------------------------------------------

function renderProcesses(data) {
  state.processes = data.processes;
  const container = document.getElementById("process-flows");
  container.innerHTML = "";
  for (const process of data.processes) {
    const wrap = el("div", "process-flow");
    wrap.appendChild(el("h3", null, `${process.label} (${process.process_id})`));
    const chain = el("div", "node-chain");
    chain.dataset.processId = process.process_id;
    const activities = process.activities || process.nodes;
    activities.forEach((node, index) => {
      const nodeEl = el("button", "node");
      nodeEl.type = "button";
      nodeEl.dataset.nodeId = node.id;
      nodeEl.appendChild(el("div", "node-id", node.id));
      const duration = node.duration.kind === "fixed"
        ? `${node.duration.hours}h`
        : node.duration.kind === "parameter"
          ? `parameter: ${node.duration.parameter}`
          : `until: ${node.duration.field}`;
      nodeEl.appendChild(el("div", "node-resource", `${node.resource || "no constrained resource"} · ${duration}`));
      nodeEl.addEventListener("click", () => renderNodeDetail(process, node));
      chain.appendChild(nodeEl);
      if (index < activities.length - 1) {
        chain.appendChild(el("span", "arrow", "→"));
      }
    });
    wrap.appendChild(chain);
    container.appendChild(wrap);
  }
}

function renderNodeDetail(process, node) {
  const transitions = node.next.length
    ? node.next.map((item) => {
        const conditions = item.conditions?.length
          ? ` [when: ${item.conditions.map((condition) => `${condition.left} ${condition.operator}`).join(" & ")}]`
          : "";
        return `${item.target}${conditions}`;
      }).join(", ")
    : "terminal";
  const effects = node.financial_effects.length
    ? node.financial_effects
        .map((item) => `${item.event}: Dr ${item.debit_account} / Cr ${item.credit_account}`)
        .join("; ")
    : "none";
  document.getElementById("node-detail").textContent =
    `${process.label} · ${node.label} (${node.id})\n` +
    `Inputs: ${node.inputs.map((item) => `${item.alias}:${item.object_type}`).join(", ")}\n` +
    `Resource: ${node.resource || "none"}; duration: ${JSON.stringify(node.duration)}\n` +
    `Next: ${transitions}\n` +
    `Start event: ${node.on_start ? node.on_start.event_type : "none"}\n` +
    `Completion event: ${node.on_complete.event_type}\n` +
    `Operations: ${node.operations.map((item) => `${item.operation} ${item.target}`).join(", ") || "none"}\n` +
    `Metrics: ${node.operational_metrics.join(", ") || "none"}\n` +
    `Financial effects: ${effects}`;
}

async function loadReference() {
  const [processes, snapshot] = await Promise.all([
    api("/api/processes"),
    api("/api/snapshot"),
  ]);
  renderProcesses(processes);
  const summary = document.getElementById("snapshot-summary");
  const source = snapshot.source_manifest;
  const asOf = new Date(snapshot.manifest.as_of_time);
  const singaporeTime = new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
  }).format(asOf);
  summary.textContent =
    `Actual State · ${snapshot.manifest.company_id} · snapshot ${snapshot.manifest.snapshot_id.slice(0, 8)} · ` +
    `${snapshot.counts.business_objects} objects · ${singaporeTime} Singapore ` +
    `(${asOf.toISOString()} UTC) · ${source.dataset} · ` +
    `source/derived/synthetic provenance retained · ` +
    `${source.embedded_exception.backlog_orders} embedded backlog orders · ` +
    `snapshot hash ${snapshot.manifest.content_hash.slice(0, 12)}… · ` +
    `process hash ${processes.content_hash.slice(0, 12)}…`;
}

// ---- Scenario builder (Task 8) ----------------------------------------------

const EVENT_FIELDS = {
  order_arrival: [
    { id: "sku", label: "Known SKU", value: "WB-H098" },
    { id: "quantity", label: "Quantity", value: "5" },
    { id: "unit_price", label: "Unit price (optional)", value: "" },
    { id: "priority", label: "Priority", value: "0", type: "number" },
  ],
  resource_capacity_changed: [
    { id: "resource_type", label: "Resource type", value: "warehouse_staff" },
    { id: "capacity_delta", label: "Capacity delta", value: "1", type: "number" },
  ],
  supplier_delivery_delayed: [
    { id: "days_delta", label: "Days delta", value: "-3" },
    { id: "purchase_order_number", label: "PO number (optional)", value: "" },
  ],
};

function renderEventFields() {
  const type = document.getElementById("event-type").value;
  const container = document.getElementById("event-fields");
  container.innerHTML = "";
  for (const field of EVENT_FIELDS[type]) {
    const label = el("label", null, field.label);
    const input = document.createElement("input");
    input.id = `field-${field.id}`;
    input.value = field.value;
    if (field.type) input.type = field.type;
    label.appendChild(input);
    container.appendChild(label);
  }
}

function collectEventPayload() {
  const type = document.getElementById("event-type").value;
  const payload = {
    event_type: type,
    effective_day: document.getElementById("event-day").value.trim(),
  };
  for (const field of EVENT_FIELDS[type]) {
    const value = document.getElementById(`field-${field.id}`).value.trim();
    if (value === "") continue;
    if (field.id === "priority" || field.id === "capacity_delta") {
      payload[field.id] = Number(value);
    } else {
      payload[field.id] = value;
    }
  }
  return payload;
}

function renderEvents() {
  const list = document.getElementById("event-list");
  list.innerHTML = "";
  state.events.forEach((event) => {
    list.appendChild(
      el("li", null, `${event.event_type} · ${JSON.stringify(event.payload)}`)
    );
  });
}

async function createSession(event) {
  event.preventDefault();
  const name = document.getElementById("session-name").value;
  const session = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  state.sessionId = session.simulation_session_id;
  state.baselineSessionId = null;
  state.baselineRunId = null;
  state.lastRun = null;
  state.events = session.scenario_events;
  document.getElementById("session-info").textContent =
    `Session ${state.sessionId.slice(0, 8)}… ready`;
  document.getElementById("event-form").hidden = false;
  document.getElementById("run-form").hidden = false;
  document.getElementById("set-baseline").disabled = true;
  document.getElementById("run-compare").disabled = true;
  document.getElementById("comparison-table").textContent = "";
  document.getElementById("run-metrics").textContent = "";
  document.getElementById("audit-evidence").textContent = "";
  document.getElementById("trace-table").textContent = "";
  document.getElementById("accounting-table").textContent = "";
  renderEvents();
}

async function addEvent(event) {
  event.preventDefault();
  const session = await api(`/api/sessions/${state.sessionId}/events`, {
    method: "POST",
    body: JSON.stringify(collectEventPayload()),
  });
  state.events = session.scenario_events;
  renderEvents();
}

async function addPreset(preset) {
  const session = await api(`/api/sessions/${state.sessionId}/events/preset`, {
    method: "POST",
    body: JSON.stringify({ preset }),
  });
  state.events = session.scenario_events;
  renderEvents();
}

// ---- Run + metrics (Task 8) -------------------------------------------------

function renderMetrics(metrics) {
  const container = document.getElementById("run-metrics");
  container.innerHTML = "";
  const table = el("table");
  for (const [key, value] of Object.entries(metrics)) {
    if (key === "resource_utilization") continue;
    const tr = el("tr");
    tr.appendChild(el("td", null, key));
    tr.appendChild(el("td", "mono", String(value)));
    table.appendChild(tr);
  }
  container.appendChild(table);
}

async function runSimulation(event) {
  event.preventDefault();
  const horizon_days = Number(document.getElementById("horizon").value);
  const random_seed = Number(document.getElementById("seed").value);
  const result = await api(`/api/sessions/${state.sessionId}/run`, {
    method: "POST",
    body: JSON.stringify({ horizon_days, random_seed }),
  });
  state.lastRun = result;
  renderMetrics(result.summary_metrics);
  setupPlayback(result);
  renderAudit(result);
  document.getElementById("set-baseline").disabled = state.baselineSessionId !== null;
  document.getElementById("run-compare").disabled = state.baselineSessionId === null;
}

// ---- Comparison panel (Task 8) ----------------------------------------------

async function pinBaseline() {
  state.baselineSessionId = state.sessionId;
  state.baselineRunId = state.lastRun ? state.lastRun.simulation_run_id : null;
  const child = await api(`/api/sessions/${state.baselineSessionId}/fork`, {
    method: "POST",
    body: JSON.stringify({ name: "Alternative scenario" }),
  });
  state.sessionId = child.simulation_session_id;
  state.lastRun = null;
  state.events = child.scenario_events;
  renderEvents();
  document.getElementById("session-info").textContent =
    `Baseline ${state.baselineSessionId.slice(0, 8)}… pinned · ` +
    `alternative ${state.sessionId.slice(0, 8)}… ready`;
  document.getElementById("run-compare").disabled = false;
  document.getElementById("set-baseline").disabled = true;
  document.getElementById("comparison-table").textContent =
    `Baseline pinned: session ${state.baselineSessionId.slice(0, 8)}…`;
}

async function runComparison() {
  const horizon_days = Number(document.getElementById("horizon").value);
  const random_seed = Number(document.getElementById("seed").value);
  const body = {
    baseline: { session_id: state.baselineSessionId, horizon_days, random_seed },
    alternative: { session_id: state.sessionId, horizon_days, random_seed },
  };
  const result = await api("/api/compare", {
    method: "POST",
    body: JSON.stringify(body),
  });
  renderComparison(result.comparison);
}

function renderComparison(comparison) {
  const container = document.getElementById("comparison-table");
  container.innerHTML = "";
  const table = el("table");
  const head = el("tr");
  ["metric", "baseline", "alternative", "difference"].forEach((h) =>
    head.appendChild(el("th", null, h))
  );
  table.appendChild(head);
  for (const [key, row] of Object.entries(comparison)) {
    const tr = el("tr");
    tr.appendChild(el("td", null, key));
    tr.appendChild(el("td", "mono", row.baseline));
    tr.appendChild(el("td", "mono", row.alternative));
    tr.appendChild(el("td", "mono", row.difference));
    table.appendChild(tr);
  }
  container.appendChild(table);
}

// ---- Trace playback (Task 9) ------------------------------------------------

function setupPlayback(result) {
  stopPlayback();
  const trace = result.event_trace;
  state.playback.trace = trace;
  state.playback.index = 0;
  state.playback.hours = trace.map((t) => Number(t.simulated_hour));
  const scrub = document.getElementById("scrub");
  scrub.max = String(Math.max(trace.length - 1, 0));
  scrub.value = "0";
  scrub.disabled = trace.length === 0;
  document.getElementById("play").disabled = trace.length === 0;
  document.getElementById("pause").disabled = trace.length === 0;
  document.getElementById("step").disabled = trace.length === 0;
  renderUtilization(result.summary_metrics.resource_utilization);
  applyPlaybackFrame(0);
}

function clearActiveNodes() {
  document.querySelectorAll(".node.active").forEach((n) => n.classList.remove("active"));
}

function applyPlaybackFrame(index) {
  const trace = state.playback.trace;
  if (trace.length === 0) return;
  const bounded = Math.max(0, Math.min(index, trace.length - 1));
  state.playback.index = bounded;
  const event = trace[bounded];
  clearActiveNodes();
  const nodeId = event.node_id;
  if (nodeId) {
    const chain = document.querySelector(`.node-chain[data-process-id="${event.process_id}"]`);
    if (chain) {
      const node = chain.querySelector(`.node[data-node-id="${nodeId}"]`);
      if (node) node.classList.add("active");
    }
  }
  document.getElementById("scrub").value = String(bounded);
  document.getElementById("clock").textContent =
    `hour ${event.simulated_hour} · seq ${event.sequence} · ${event.event_type}`;
}

function stepPlayback() {
  applyPlaybackFrame(state.playback.index + 1);
}

function playPlayback() {
  stopPlayback();
  state.playback.timer = window.setInterval(() => {
    if (state.playback.index >= state.playback.trace.length - 1) {
      stopPlayback();
      return;
    }
    applyPlaybackFrame(state.playback.index + 1);
  }, 400);
}

function stopPlayback() {
  if (state.playback.timer !== null) {
    window.clearInterval(state.playback.timer);
    state.playback.timer = null;
  }
}

function renderUtilization(utilization) {
  const container = document.getElementById("utilization");
  container.innerHTML = "";
  for (const [resource, value] of Object.entries(utilization || {})) {
    const meter = el("div", "utilization-meter");
    meter.appendChild(el("div", "muted", `${resource}: ${value}`));
    const bar = el("div", "utilization-bar");
    const fill = el("div", "utilization-fill");
    const pct = Math.max(0, Math.min(100, Number(value) * 100));
    fill.style.width = `${pct}%`;
    bar.appendChild(fill);
    meter.appendChild(bar);
    container.appendChild(meter);
  }
}

function renderTable(containerId, headers, rows) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  const table = el("table");
  const head = el("tr");
  headers.forEach((header) => head.appendChild(el("th", null, header)));
  table.appendChild(head);
  rows.forEach((row) => {
    const tr = el("tr");
    row.forEach((value) => tr.appendChild(el("td", "mono", String(value))));
    table.appendChild(tr);
  });
  container.appendChild(table);
}

function renderAudit(result) {
  const evidence = document.getElementById("audit-evidence");
  evidence.textContent =
    `Simulated State · snapshot ${result.snapshot_hash} · process ${result.process_definition_hash} · ` +
    `scenario ${result.scenario_event_hash} · result ${result.result_hash} · ` +
    `horizon ${result.horizon_days} days · seed ${result.random_seed} · ` +
    `Actual State unchanged: ${result.actual_state_unchanged}`;
  renderTable(
    "trace-table",
    ["seq", "hour", "process", "node", "event", "object"],
    result.event_trace.slice(0, 100).map((event) => [
      event.sequence,
      event.simulated_hour,
      event.process_id,
      event.node_id || "system",
      event.event_type,
      event.object_id,
    ])
  );
  renderTable(
    "accounting-table",
    ["hour", "event", "object", "balanced lines"],
    result.accounting_impacts.slice(0, 100).map((impact) => [
      impact.simulated_hour,
      impact.event_type,
      impact.object_id,
      impact.lines
        .map((line) => `${line.account}: Dr ${line.debit} / Cr ${line.credit}`)
        .join("; "),
    ])
  );
}

// ---- Business module views -------------------------------------------------

function moduleData(envelope) {
  if (!envelope || envelope.schema_version !== "business-modules-v1") {
    throw new Error("Unsupported business module response contract");
  }
  return envelope.data;
}

function formatSgd(value) {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatNumber(value, maximumFractionDigits = 0) {
  return new Intl.NumberFormat("en-SG", { maximumFractionDigits }).format(Number(value));
}

function formatPercent(value) {
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function humanize(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderModuleStats(containerId, entries) {
  const container = document.getElementById(containerId);
  container.classList.remove("loading-block");
  container.innerHTML = "";
  entries.forEach(([label, value, tone = ""]) => {
    const card = el("div", `module-stat ${tone}`.trim());
    card.appendChild(el("strong", null, String(value)));
    card.appendChild(el("span", null, label));
    container.appendChild(card);
  });
}

function renderDistribution(containerId, rows, total) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  rows.forEach(([label, value, tone = ""]) => {
    const row = el("div", "distribution-row");
    const heading = el("div", "distribution-label");
    heading.appendChild(el("span", null, humanize(label)));
    heading.appendChild(el("b", null, String(value)));
    row.appendChild(heading);
    const track = el("div", "distribution-track");
    const fill = el("div", `distribution-fill ${tone}`.trim());
    fill.style.width = `${total ? Math.max(2, Number(value) / total * 100) : 0}%`;
    track.appendChild(fill);
    row.appendChild(track);
    container.appendChild(row);
  });
}

function renderOverview(data) {
  const h = data.headline;
  renderModuleStats("overview-kpis", [
    ["Current order value", formatSgd(h.current_order_value)],
    ["Sales backlog", formatNumber(h.backlog_count), "attention"],
    ["Reorder candidates", formatNumber(h.reorder_candidate_count), "attention"],
    ["Cash balance", formatSgd(h.cash)],
    ["Derived service cases", formatNumber(h.service_case_count), "attention"],
    ["Overdue orders", formatNumber(h.overdue_orders), "critical"],
  ]);
  const container = document.getElementById("overview-modules");
  container.innerHTML = "";
  data.modules.forEach((item, index) => {
    const button = el("button", "module-launch");
    button.type = "button";
    button.appendChild(el("span", "module-launch-number", String(index + 1).padStart(2, "0")));
    const copy = el("span", "module-launch-copy");
    copy.appendChild(el("b", null, item.label));
    copy.appendChild(el("small", null, item.signal));
    button.appendChild(copy);
    button.appendChild(el("span", "module-launch-arrow", "→"));
    button.addEventListener("click", () => showFunctionPage(item.id));
    container.appendChild(button);
  });
}

function renderSales(data) {
  const s = data.summary;
  renderModuleStats("sales-kpis", [
    ["Orders", formatNumber(s.order_count)],
    ["Current order value", formatSgd(s.current_order_value)],
    ["Fulfilment rate", formatPercent(s.fulfilment_rate)],
    ["Backlog orders", formatNumber(s.backlog_count), "attention"],
    ["Backlog value", formatSgd(s.backlog_value), "attention"],
  ]);
  const statusRows = Object.entries(data.status_counts);
  renderDistribution("sales-status", statusRows, s.order_count);
  renderTable(
    "sales-skus",
    ["SKU", "Orders", "Order value"],
    data.top_skus.map((row) => [row.sku, row.order_count, formatSgd(row.order_value)])
  );
  renderTable(
    "sales-backlog",
    ["Order", "SKU", "Amount", "Qty", "Current step", "Priority"],
    data.backlog_orders.map((row) => [
      row.order_number,
      row.sku,
      formatSgd(row.amount),
      formatNumber(row.quantity),
      humanize(row.current_step),
      row.priority,
    ])
  );
  document.getElementById("sales-note").textContent = data.measurement_note;
}

function renderInventory(data) {
  const s = data.summary;
  renderModuleStats("inventory-kpis", [
    ["Active SKUs", formatNumber(s.sku_count)],
    ["Warehouses", formatNumber(s.warehouse_count)],
    ["On-hand units", formatNumber(s.on_hand_units)],
    ["Value at standard cost", formatSgd(s.inventory_value_at_standard_cost)],
    ["Reorder candidates", formatNumber(s.reorder_candidate_count), "attention"],
    ["Critical", formatNumber(s.critical_candidate_count), "critical"],
  ]);
  const riskOrder = ["critical", "high", "medium", "low"];
  const riskRows = riskOrder
    .filter((risk) => Object.hasOwn(data.risk_counts, risk))
    .map((risk) => [risk, data.risk_counts[risk], risk]);
  renderDistribution("inventory-risks", riskRows, s.sku_count);
  renderTable(
    "inventory-candidates",
    ["SKU", "Item", "Stock", "Reorder point", "Recommended", "Risk"],
    data.reorder_candidates.map((row) => [
      row.sku,
      row.name,
      formatNumber(row.current_stock),
      formatNumber(row.reorder_point),
      formatNumber(row.recommended_quantity),
      humanize(row.risk_level),
    ])
  );
  document.getElementById("inventory-note").textContent = data.measurement_note;
}

function inventoryToolData(envelope, expectedTool) {
  if (!envelope || envelope.tool_name !== expectedTool) {
    throw new Error("Unsupported inventory tool response contract");
  }
  if (envelope.status !== "ok") {
    throw new Error(envelope.error_message || "Inventory tool execution failed");
  }
  return envelope.data;
}

function setInventoryStatus(id, message, tone = "") {
  const status = document.getElementById(id);
  status.textContent = message;
  status.className = `inventory-inline-status ${tone}`.trim();
}

function renderInventoryCandidates(data) {
  document.getElementById("inventory-candidate-source").textContent =
    `Actual snapshot · ${String(data.snapshot_id).slice(0, 8)}`;
  setInventoryStatus(
    "inventory-candidate-status",
    `${formatNumber(data.candidate_count)} matching candidates · ${formatNumber(data.total_recommended_quantity)} total recommended units`,
    data.candidate_count ? "success" : "empty"
  );
  renderTable(
    "inventory-candidates",
    ["SKU", "Item", "Stock", "Reorder point", "Target stock", "Recommended", "Risk"],
    (data.candidates || []).map((row) => [
      row.sku,
      row.name,
      formatNumber(row.current_stock),
      formatNumber(row.reorder_point),
      formatNumber(row.target_stock),
      formatNumber(row.recommended_quantity),
      humanize(row.risk_level),
    ])
  );
  if (!data.candidates?.length) {
    document.getElementById("inventory-candidates").appendChild(
      el("p", "inventory-empty-state", "No reorder candidate matched this filter.")
    );
  }
}

async function loadInventoryCandidates(event) {
  event?.preventDefault?.();
  const requestId = ++state.inventoryCandidateRequest;
  const button = document.getElementById("inventory-refresh-candidates");
  const riskLevel = document.getElementById("inventory-risk-level").value;
  const topN = Number(document.getElementById("inventory-top-n").value);
  button.disabled = true;
  setInventoryStatus("inventory-candidate-status", "Loading candidates from the Actual State…", "loading");
  try {
    const envelope = await api(
      `/api/v1/modules/inventory/reorder-candidates?risk_level=${encodeURIComponent(riskLevel)}&top_n=${encodeURIComponent(topN)}`
    );
    if (requestId !== state.inventoryCandidateRequest) return;
    renderInventoryCandidates(inventoryToolData(envelope, "list_inventory_reorder_candidates"));
  } catch (error) {
    if (requestId !== state.inventoryCandidateRequest) return;
    setInventoryStatus("inventory-candidate-status", `Could not load candidates: ${error.message}`, "error");
  } finally {
    if (requestId === state.inventoryCandidateRequest) button.disabled = false;
  }
}

function renderInventoryRecommendation(recommendation) {
  const container = document.getElementById("inventory-recommendation");
  container.innerHTML = "";
  const card = el("section", "inventory-recommendation-card");
  const heading = el("div", "inventory-section-heading");
  const copy = el("div");
  copy.appendChild(el("p", "module-kicker", "RECOMMENDED FOR HUMAN REVIEW"));
  copy.appendChild(el("h3", null, humanize(recommendation.recommended_strategy)));
  heading.appendChild(copy);
  heading.appendChild(el("span", "badge", humanize(recommendation.selection_method)));
  card.appendChild(heading);
  const metrics = el("div", "inventory-recommendation-metrics");
  [
    ["Replenishment qty", formatNumber(recommendation.replenishment_quantity)],
    ["Backlog reduction", formatNumber(recommendation.backlog_reduction)],
    ["Fulfilment improvement", formatPercent(recommendation.fulfilment_improvement)],
    ["Gross profit improvement", formatSgd(recommendation.gross_profit_improvement)],
    ["Cash improvement", formatSgd(recommendation.cash_improvement)],
  ].forEach(([label, value]) => {
    const metric = el("div", "inventory-recommendation-metric");
    metric.appendChild(el("strong", null, value));
    metric.appendChild(el("span", null, label));
    metrics.appendChild(metric);
  });
  card.appendChild(metrics);
  container.appendChild(card);
}

function appendMetricDetails(cell, run) {
  const details = el("details", "inventory-run-details");
  details.appendChild(el("summary", null, "More metrics and evidence"));
  const m = run.metrics;
  const lines = [
    `Average waiting: ${formatNumber(m.average_waiting_hours, 2)} hours`,
    `Revenue: ${formatSgd(m.revenue)}`,
    `Cost of goods sold: ${formatSgd(m.cost_of_goods_sold)}`,
    `Accounts receivable: ${formatSgd(m.accounts_receivable)}`,
    `Accounts payable: ${formatSgd(m.accounts_payable)}`,
    `Resource utilization: ${Object.entries(m.resource_utilization || {}).map(([key, value]) => `${humanize(key)} ${formatPercent(value)}`).join(", ") || "Not available"}`,
    `Result hash: ${run.result_hash}`,
  ];
  details.appendChild(el("pre", "inventory-evidence-code", lines.join("\n")));
  cell.appendChild(details);
}

function renderInventoryStrategyRuns(data) {
  const container = document.getElementById("inventory-strategy-table");
  container.innerHTML = "";
  const table = el("table", "inventory-strategy-table");
  const head = el("thead");
  const headerRow = el("tr");
  ["Strategy", "Events", "Replenishment qty", "Ending backlog", "Fulfilment", "Stockouts", "Ending inventory", "Inventory value", "Gross profit", "Ending cash", "Minimum cash", "Run ID"].forEach((label) => headerRow.appendChild(el("th", null, label)));
  head.appendChild(headerRow);
  table.appendChild(head);
  const body = el("tbody");
  (data.strategy_runs || []).forEach((run) => {
    const row = el("tr", run.strategy === data.recommendation.recommended_strategy ? "recommended-row" : "");
    const strategyCell = el("td");
    strategyCell.appendChild(el("strong", null, humanize(run.strategy)));
    if (run.strategy === data.recommendation.recommended_strategy) strategyCell.appendChild(el("span", "recommended-label", "Recommended"));
    appendMetricDetails(strategyCell, run);
    row.appendChild(strategyCell);
    const m = run.metrics;
    [
      run.event_count,
      formatNumber(run.replenishment_quantity),
      formatNumber(m.ending_backlog),
      formatPercent(m.fulfilment_rate),
      formatNumber(m.stockout_count),
      formatNumber(m.ending_inventory_quantity),
      formatSgd(m.ending_inventory_value),
      formatSgd(m.gross_profit),
      formatSgd(m.ending_cash),
      formatSgd(m.minimum_cash),
      run.simulation_run_id,
    ].forEach((value, index) => row.appendChild(el("td", index === 10 ? "mono run-id-cell" : "mono", String(value))));
    body.appendChild(row);
  });
  table.appendChild(body);
  container.appendChild(table);
}

function renderInventoryShortages(shortages) {
  const rows = Object.entries(shortages || {});
  const container = document.getElementById("inventory-shortages");
  if (!rows.length) {
    container.innerHTML = "";
    container.appendChild(el("p", "inventory-empty-state", "No demand shortage was found for the current snapshot."));
    return;
  }
  renderTable("inventory-shortages", ["SKU", "Shortage quantity"], rows.map(([sku, value]) => [sku, formatNumber(value)]));
}

function renderInventoryEvidence(data) {
  const recommendation = data.recommendation;
  const container = document.getElementById("inventory-evidence-content");
  container.innerHTML = "";
  const columns = el("div", "inventory-evidence-grid");
  const assumptions = el("div");
  assumptions.appendChild(el("h4", null, "Assumptions"));
  const assumptionList = el("ul");
  recommendation.assumptions.forEach((item) => assumptionList.appendChild(el("li", null, item)));
  assumptions.appendChild(assumptionList);
  const limitations = el("div");
  limitations.appendChild(el("h4", null, "Limitations"));
  const limitationList = el("ul");
  recommendation.limitations.forEach((item) => limitationList.appendChild(el("li", null, item)));
  limitations.appendChild(limitationList);
  columns.appendChild(assumptions);
  columns.appendChild(limitations);
  container.appendChild(columns);
  const evidenceLines = [
    `Snapshot ID: ${data.snapshot_id}`,
    `Snapshot hash: ${data.snapshot_hash}`,
    `Baseline run ID: ${recommendation.baseline_run_id}`,
    `Recommended run ID: ${recommendation.recommended_run_id}`,
    ...(data.strategy_runs || []).map((run) => `${humanize(run.strategy)}: run ${run.simulation_run_id} · hash ${run.result_hash}`),
  ];
  container.appendChild(el("pre", "inventory-evidence-code", evidenceLines.join("\n")));
}

function renderInventoryStrategyResult(data) {
  renderInventoryRecommendation(data.recommendation);
  renderInventoryStrategyRuns(data);
  renderInventoryShortages(data.demand_shortages);
  document.getElementById("inventory-decision-boundary").textContent = data.recommendation.actual_state_unchanged
    ? "Simulation only — actual inventory was not changed. No purchase order was created. A human must review any action."
    : "Actual-state protection could not be confirmed. Do not act on this result.";
  renderInventoryEvidence(data);
  document.getElementById("inventory-strategy-results").hidden = false;
  state.inventoryStrategyHasResult = true;
}

function markInventoryStrategyStale() {
  if (!state.inventoryStrategyHasResult || state.inventoryStrategyBusy) return;
  setInventoryStatus("inventory-strategy-status", "Parameters changed — the displayed result is stale. Run the comparison again.", "stale");
}

async function runInventoryStrategyComparison(event) {
  event.preventDefault();
  if (state.inventoryStrategyBusy) return;
  state.inventoryStrategyBusy = true;
  const requestId = ++state.inventoryStrategyRequest;
  const button = document.getElementById("inventory-compare-strategies");
  button.disabled = true;
  button.textContent = "Comparing…";
  setInventoryStatus("inventory-strategy-status", "Running four isolated simulation strategies…", "loading");
  try {
    const envelope = await api("/api/v1/modules/inventory/strategy-comparison", {
      method: "POST",
      body: JSON.stringify({
        horizon_days: Number(document.getElementById("inventory-horizon-days").value),
        effective_day: document.getElementById("inventory-effective-day").value,
        random_seed: Number(document.getElementById("inventory-random-seed").value),
      }),
    });
    if (requestId !== state.inventoryStrategyRequest) return;
    const data = inventoryToolData(envelope, "compare_inventory_replenishment_strategies");
    renderInventoryStrategyResult(data);
    setInventoryStatus("inventory-strategy-status", "Comparison completed. Review the recommendation and evidence below.", "success");
  } catch (error) {
    if (requestId !== state.inventoryStrategyRequest) return;
    setInventoryStatus("inventory-strategy-status", `Comparison failed: ${error.message}`, "error");
  } finally {
    if (requestId === state.inventoryStrategyRequest) {
      state.inventoryStrategyBusy = false;
      button.disabled = false;
      button.textContent = "Compare strategies";
    }
  }
}

function renderAccounting(data) {
  const s = data.summary;
  renderModuleStats("accounting-kpis", [
    ["Cash", formatSgd(s.cash)],
    ["Accounts receivable", formatSgd(s.accounts_receivable)],
    ["Accounts payable", formatSgd(s.accounts_payable)],
    ["Gross profit", formatSgd(s.gross_profit)],
    ["Gross margin", formatPercent(s.gross_margin)],
    ["Working capital", formatSgd(s.working_capital)],
  ]);
  renderTable(
    "accounting-balances",
    ["Account", "Amount", "Currency", "Origin"],
    data.balances.map((row) => [
      humanize(row.account_code),
      formatSgd(row.amount),
      row.currency,
      humanize(row.data_origin),
    ])
  );
  document.getElementById("accounting-note").textContent = data.measurement_note;
}

function renderOperations(data) {
  const s = data.summary;
  renderModuleStats("operations-kpis", [
    ["Business objects", formatNumber(s.business_object_count)],
    ["Processes", formatNumber(s.process_count)],
    ["Active steps", formatNumber(s.active_node_count)],
    ["Resource pools", formatNumber(s.resource_count)],
    ["Order to cash", formatNumber(s.order_to_cash_objects)],
    ["Procure to pay", formatNumber(s.procure_to_pay_objects)],
  ]);
  renderTable(
    "operations-nodes",
    ["Current process step", "Objects"],
    data.objects_by_current_node.map((row) => [humanize(row.node_id), row.object_count])
  );
  renderTable(
    "operations-resources",
    ["Process", "Step", "Resource", "Capacity", "Origin"],
    data.resources.map((row) => [
      humanize(row.process_id),
      humanize(row.node_id),
      humanize(row.resource_type),
      formatNumber(row.capacity_units),
      humanize(row.data_origin),
    ])
  );
  document.getElementById("operations-note").textContent = data.measurement_note;
}

async function loadBusinessModules() {
  const [overview, sales, inventory, accounting, operations] = await Promise.all([
    api("/api/v1/modules/overview"),
    api("/api/v1/modules/sales"),
    api("/api/v1/modules/inventory"),
    api("/api/v1/modules/accounting"),
    api("/api/v1/modules/operations"),
  ]);
  renderOverview(moduleData(overview));
  renderSales(moduleData(sales));
  renderInventory(moduleData(inventory));
  renderAccounting(moduleData(accounting));
  renderOperations(moduleData(operations));
  await loadInventoryCandidates();
}

// ---- Assistant chat (Task 10) -----------------------------------------------

function appendChat(role, text) {
  document.getElementById("assistant-welcome").hidden = true;
  const log = document.getElementById("chat-log");
  const msg = el("div", `chat-message ${role}`, text);
  msg.setAttribute?.("aria-label", role === "user" ? "You" : "Business Coordinator");
  log.appendChild(msg);
  document.querySelector(".assistant-conversation")?.scrollTo?.({ top: log.scrollHeight, behavior: "smooth" });
}

function fillAssistantPrompt(prompt) {
  const input = document.getElementById("chat-input");
  input.value = prompt;
  input.focus?.();
}

function handleAssistantComposerKeydown(event) {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  document.getElementById("chat-form").requestSubmit?.();
}

async function sendChat(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message || state.chatBusy) return;
  appendChat("user", message);
  input.value = "";
  state.chatBusy = true;
  const button = document.querySelector("#chat-form button");
  button.disabled = true;
  button.setAttribute?.("aria-label", "Coordinator is working");
  try {
    const reply = await api("/api/assistant", {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: state.conversationId,
        session_id: state.sessionId,
        run_id: state.lastRun ? state.lastRun.simulation_run_id : null,
      }),
    });
    appendChat("assistant", `${reply.reply} [${reply.status}]`);
    state.conversationId = reply.conversation_id;
    const trace = el("details", "chat-evidence");
    trace.appendChild(el("summary", null,
      `Evidence: ${reply.evidence.length} tool calls · Run ${reply.agent_run_id}`));
    for (const item of reply.evidence) {
      if (item.tool_name !== "search_public_events") continue;
      if (item.status === "error") {
        trace.appendChild(el("p", "muted", `Web search: ${item.error_message}`));
        continue;
      }
      for (const source of item.data?.sources || []) {
        let url;
        try { url = new URL(source.url); } catch { continue; }
        if (!["http:", "https:"].includes(url.protocol)) continue;
        const link = el("a", null, source.title || source.url);
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        const row = el("p");
        row.appendChild(link);
        trace.appendChild(row);
      }
    }
    trace.appendChild(el("pre", null, JSON.stringify(reply.evidence, null, 2)));
    document.getElementById("chat-log").appendChild(trace);
    if (reply.status === "completed") {
      reply.evidence.filter((item) =>
        item.status === "ok" && item.tool_name === "recommend_resolution"
      ).forEach((item) => {
        const complaintId = item.data.result.complaintId;
        const review = el("button", null, `Review CRM recommendation · ${complaintId}`);
        review.type = "button";
        review.addEventListener("click", () =>
          runAction("Loading CRM evidence…", () => openCrmRecommendation(reply, item))
        );
        trace.appendChild(review);
      });
    }
  } catch (error) {
    appendChat("assistant", `Request failed: ${error.message}`);
    throw error;
  } finally {
    state.chatBusy = false;
    button.disabled = false;
    button.setAttribute?.("aria-label", "Send message");
  }
}

// ---- CRM service recovery ---------------------------------------------------

function crmData(envelope) {
  if (!envelope || envelope.schema_version !== "crm-api-v1") {
    throw new Error("Unsupported CRM response contract");
  }
  return envelope.data;
}

function renderCrmSummary(summary) {
  const container = document.getElementById("crm-summary");
  container.innerHTML = "";
  const entries = [
    ["Customers", summary.customerCount],
    ["Order-service cases", summary.serviceCaseCount],
    ["High pending-order exception share", summary.highRiskCustomers],
    ["Orders past due", summary.overdueOrders],
    ["First-response records", summary.unrespondedComplaints],
    ["A-tier value", summary.aTierCustomers],
  ];
  for (const [label, value] of entries) {
    const card = el("div", "crm-stat");
    card.appendChild(el("strong", null, value == null ? "Unavailable" : String(value)));
    card.appendChild(el("span", null, label));
    container.appendChild(card);
  }
}

function renderCrmComplaints(rows) {
  const container = document.getElementById("crm-complaints");
  container.innerHTML = "";
  const table = el("table");
  const head = el("tr");
  ["Case", "Customer", "Priority", "Order due date", "Owner"].forEach((label) =>
    head.appendChild(el("th", null, label))
  );
  table.appendChild(head);
  rows.forEach((item) => {
    const tr = el("tr", "crm-case-row");
    const linkCell = el("td");
    const button = el("button", "text-button", item.id);
    button.type = "button";
    button.addEventListener("click", () =>
      runAction(`Investigating ${item.id}…`, () => selectCrmComplaint(item.id))
    );
    linkCell.appendChild(button);
    tr.appendChild(linkCell);
    tr.appendChild(el("td", null, item.customerId));
    tr.appendChild(el("td", `priority-${item.priorityLevel.toLowerCase()}`, `${item.priorityLevel} · ${item.priorityScore}`));
    tr.appendChild(el("td", null, item.overdueHours > 0 ? `${item.overdueHours.toFixed(1)}h past due` : "Not overdue"));
    tr.appendChild(el("td", null, item.ownerRole));
    table.appendChild(tr);
  });
  container.appendChild(table);
}

function renderCrmDetail(item) {
  const detail = document.getElementById("crm-detail");
  detail.innerHTML = "";
  detail.classList.remove("muted");
  const investigation = item.investigation;
  const customer = item.customer;
  detail.appendChild(el("h4", null, `${item.id} · ${item.issue}`));
  detail.appendChild(el("p", null,
    `${customer.name} · value ${customer.valueTier}/${customer.valueScore} · pending-order exception share ${customer.riskScore}%`));
  const scores = customer.scoreDetails;
  if (scores) {
    detail.appendChild(el("p", null,
      `RFM (${scores.windowDays} days): R ${scores.components.recency ?? "N/A"}, F ${scores.components.frequency ?? "N/A"}, M ${scores.components.monetary ?? "N/A"}. Equal weights; ${scores.eligibleOrderCount} eligible orders; cohort ${scores.cohortSize}.`));
    detail.appendChild(el("p", "muted",
      `${scores.policyVersion}: ordered value, not paid spend. ${scores.coverage}. ${scores.calibration}.`));
    if (scores.smallSample || scores.riskSmallSample) {
      detail.appendChild(el("p", "muted", "Small sample: interpret scores cautiously; this is not a churn probability."));
    }
  }
  detail.appendChild(el("p", null, `Next action: ${item.nextAction}`));
  const evidence = el("ul", "crm-evidence");
  item.reasons.forEach((reason) => evidence.appendChild(el("li", null, reason)));
  detail.appendChild(evidence);
  const recommendation = investigation.recommendation;
  detail.appendChild(el("p", "crm-recommendation",
    `Recommended review: ${recommendation.label} · ${recommendation.currency || "SGD"} ${recommendation.estimatedCost ?? "unavailable"} · ETA ${recommendation.resolutionDays ?? "unknown"}. ${investigation.rationale}`));
  detail.appendChild(el("p", "muted", investigation.boundary));
  const simulate = el("button", null, "Test CRM capacity intervention with Agent");
  simulate.type = "button";
  simulate.addEventListener("click", () => {
    showFunctionPage("assistant");
    document.getElementById("chat-input").value =
      `Investigate ${item.id}. First use CRM actual evidence, then call ` +
      `analyze_crm_service_capacity with 2 additional workers, a 7-day horizon and seed 42. ` +
      `Separate facts from the unproven cause hypothesis, report the baseline-versus-scenario ` +
      `metrics, and draft a CRM service-recovery action plan for human review.`;
  });
  detail.appendChild(simulate);

  const select = document.getElementById("crm-resolution");
  select.innerHTML = "";
  investigation.options.forEach((option) => {
    const node = document.createElement("option");
    node.value = option.id;
    node.textContent = `${option.recommended ? "Recommended · " : ""}${option.label} · ${option.currency || "SGD"} ${option.estimatedCost ?? "unavailable"} · ${option.feasible ? "feasible for review" : "not currently feasible"}`;
    node.selected = option.recommended;
    node.disabled = !option.feasible;
    select.appendChild(node);
  });
  document.getElementById("crm-reply").value = item.replyDraft;
  document.getElementById("crm-internal").value = item.internalDraft;
  document.getElementById("crm-proposal-form").hidden = false;
}

async function selectCrmComplaint(complaintId) {
  const envelope = await api(`/api/v1/crm/complaints/${encodeURIComponent(complaintId)}`);
  state.crmComplaintId = complaintId;
  state.crmComplaint = crmData(envelope);
  state.crmSource = null;
  renderCrmDetail(state.crmComplaint);
}

async function openCrmRecommendation(run, evidence) {
  showFunctionPage("crm");
  await selectCrmComplaint(evidence.data.result.complaintId);
  state.crmSource = {
    sourceAgentRunId: run.agent_run_id,
    sourceToolCallId: evidence.tool_call_id,
  };
  document.getElementById("crm-detail").appendChild(
    el("p", "muted", `Source AgentRun ${run.agent_run_id} · Evidence ${evidence.tool_call_id}`)
  );
}

function renderCrmProposals(rows) {
  const container = document.getElementById("crm-proposals");
  container.innerHTML = "";
  if (!rows.length) {
    container.appendChild(el("p", "muted", "No proposals have been submitted."));
    return;
  }
  const table = el("table");
  const head = el("tr");
  ["Case", "Resolution", "Cost", "Status", "Review"].forEach((label) =>
    head.appendChild(el("th", null, label))
  );
  table.appendChild(head);
  rows.forEach((item) => {
    const tr = el("tr");
    tr.appendChild(el("td", null, item.complaintId));
    tr.appendChild(el("td", null, item.resolutionLabel));
    tr.appendChild(el("td", "mono", `${item.currency} ${item.estimatedCost}`));
    tr.appendChild(el("td", null, item.status));
    const actions = el("td", "review-actions");
    if (item.status === "Pending Review") {
      ["Approved", "Rejected"].forEach((decision) => {
        const button = el("button", decision === "Approved" ? "approve" : "reject", decision);
        button.type = "button";
        button.addEventListener("click", () =>
          runAction(`${decision} ${item.id}…`, () => decideCrmProposal(item.id, decision))
        );
        actions.appendChild(button);
      });
    } else {
      actions.appendChild(el("span", "muted", item.reviewer || "Reviewed"));
    }
    const audit = el("details");
    audit.appendChild(el("summary", null, "Evidence / review audit"));
    audit.appendChild(el("pre", null, JSON.stringify({
      datasetReference: item.datasetReference,
      sourceAgentRunId: item.sourceAgentRunId,
      sourceToolCallId: item.sourceToolCallId,
      audit: item.audit,
      effect: item.effect,
    }, null, 2)));
    actions.appendChild(audit);
    tr.appendChild(actions);
    table.appendChild(tr);
  });
  container.appendChild(table);
}

async function loadCrmProposals() {
  const envelope = await api("/api/v1/crm/proposals");
  renderCrmProposals(crmData(envelope));
}

async function submitCrmProposal(event) {
  event.preventDefault();
  if (!state.crmComplaintId) return;
  await api("/api/v1/crm/proposals", {
    method: "POST",
    body: JSON.stringify({
      complaintId: state.crmComplaintId,
      resolutionId: document.getElementById("crm-resolution").value,
      replyDraft: document.getElementById("crm-reply").value,
      internalDraft: document.getElementById("crm-internal").value,
      ...(state.crmSource || {}),
    }),
  });
  await loadCrmProposals();
}

async function decideCrmProposal(proposalId, decision) {
  const reviewer = document.getElementById("crm-reviewer").value.trim();
  if (!reviewer) throw new Error("Enter a reviewer name before deciding");
  await api(`/api/v1/crm/proposals/${proposalId}/decision`, {
    method: "POST",
    body: JSON.stringify({
      decision,
      reviewer,
      note: document.getElementById("crm-review-note").value.trim(),
    }),
  });
  await loadCrmProposals();
}

async function loadCrm() {
  const [summaryEnvelope, complaintsEnvelope, proposalsEnvelope, provenanceEnvelope] =
    await Promise.all([
      api("/api/v1/crm/summary"),
      api("/api/v1/crm/complaints?limit=24"),
      api("/api/v1/crm/proposals"),
      api("/api/v1/crm/provenance"),
    ]);
  renderCrmSummary(crmData(summaryEnvelope));
  renderCrmComplaints(crmData(complaintsEnvelope));
  renderCrmProposals(crmData(proposalsEnvelope));
  document.getElementById("crm-provenance").textContent =
    JSON.stringify(crmData(provenanceEnvelope), null, 2);
}

// ---- Business module navigation ---------------------------------------------

const FUNCTION_PAGES = {
  overview: {
    eyebrow: "BUSINESS PERFORMANCE",
    title: "Executive Overview",
    description: "See the most important signals across sales, inventory, finance, operations and customer relationships.",
  },
  sales: {
    eyebrow: "ORDER TO CASH",
    title: "Sales",
    description: "Track order value, fulfilment progress and the backlog investigation queue.",
  },
  inventory: {
    eyebrow: "STOCK CONTROL",
    title: "Inventory",
    description: "Monitor on-hand stock and review deterministic replenishment signals.",
  },
  accounting: {
    eyebrow: "FINANCIAL ANCHOR",
    title: "Accounting",
    description: "Review labelled balances, margin and working-capital indicators.",
  },
  operations: {
    eyebrow: "PROCESS STATE AND SIMULATION",
    title: "Operations",
    description: "Observe workload, test what-if events and inspect simulation evidence.",
  },
  crm: {
    eyebrow: "CUSTOMER OPERATIONS",
    title: "Customer Relationships",
    description: "Review RFM customer segments and pending-order exception share, then investigate service cases with human approval.",
  },
  assistant: {
    eyebrow: "AGENT COORDINATION",
    title: "AI Coordinator",
    description: "Ask the shared Runtime to select grounded tools across sales, inventory, CRM and simulation.",
  },
};

function showFunctionPage(pageId, updateHash = true) {
  const config = FUNCTION_PAGES[pageId] || FUNCTION_PAGES.overview;
  const resolvedId = FUNCTION_PAGES[pageId] ? pageId : "overview";
  document.querySelectorAll("[data-page]").forEach((view) => {
    const active = view.dataset.page === resolvedId;
    view.hidden = !active;
    view.classList.toggle("active", active);
  });
  document.querySelectorAll("[data-page-target]").forEach((button) => {
    const active = button.dataset.pageTarget === resolvedId;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.getElementById("page-eyebrow").textContent = config.eyebrow;
  document.getElementById("page-title").textContent = config.title;
  document.getElementById("page-description").textContent = config.description;
  document.title = `${config.title} · HomeNest`;
  if (updateHash && window.location.hash !== `#${resolvedId}`) {
    window.history.replaceState(null, "", `#${resolvedId}`);
  }
  document.querySelector(".app-main")?.scrollTo?.({ top: 0, behavior: "smooth" });
}

function initFunctionNavigation() {
  document.querySelectorAll("[data-page-target]").forEach((button) => {
    button.addEventListener("click", () => showFunctionPage(button.dataset.pageTarget));
  });
  const requested = window.location.hash.slice(1);
  showFunctionPage(FUNCTION_PAGES[requested] ? requested : "overview", false);
  window.addEventListener("hashchange", () => {
    const pageId = window.location.hash.slice(1);
    if (FUNCTION_PAGES[pageId]) showFunctionPage(pageId, false);
  });
}

// ---- Wiring -----------------------------------------------------------------

function init() {
  initFunctionNavigation();
  document.getElementById("session-form").addEventListener("submit", (event) =>
    runAction("Creating session…", () => createSession(event))
  );
  document.getElementById("event-form").addEventListener("submit", (event) =>
    runAction("Adding scenario event…", () => addEvent(event))
  );
  document.getElementById("event-type").addEventListener("change", renderEventFields);
  document
    .getElementById("preset-warehouse")
    .addEventListener("click", () =>
      runAction("Adding warehouse preset…", () => addPreset("warehouse_capacity_increase"))
    );
  document
    .getElementById("preset-supplier")
    .addEventListener("click", () =>
      runAction("Adding supplier preset…", () => addPreset("expedited_supplier_delivery"))
    );
  document.getElementById("run-form").addEventListener("submit", (event) =>
    runAction("Running deterministic simulation…", () => runSimulation(event))
  );
  document.getElementById("set-baseline").addEventListener("click", () =>
    runAction("Forking an isolated alternative…", pinBaseline)
  );
  document.getElementById("run-compare").addEventListener("click", () =>
    runAction("Comparing isolated sessions…", runComparison)
  );
  document.getElementById("play").addEventListener("click", playPlayback);
  document.getElementById("pause").addEventListener("click", stopPlayback);
  document.getElementById("step").addEventListener("click", stepPlayback);
  document
    .getElementById("scrub")
    .addEventListener("input", (e) => applyPlaybackFrame(Number(e.target.value)));
  document.getElementById("chat-form").addEventListener("submit", (event) =>
    runAction("OpenClaw is analysing…", () => sendChat(event))
  );
  document.getElementById("chat-input").addEventListener("keydown", handleAssistantComposerKeydown);
  document.querySelectorAll("[data-assistant-prompt]").forEach((button) =>
    button.addEventListener("click", () => fillAssistantPrompt(button.dataset.assistantPrompt))
  );
  document.getElementById("crm-proposal-form").addEventListener("submit", (event) =>
    runAction("Submitting a review-only proposal…", () => submitCrmProposal(event))
  );
  document.getElementById("inventory-candidate-form").addEventListener("submit", loadInventoryCandidates);
  document.getElementById("inventory-strategy-form").addEventListener("submit", runInventoryStrategyComparison);
  ["inventory-horizon-days", "inventory-effective-day", "inventory-random-seed"].forEach((id) =>
    document.getElementById(id).addEventListener("input", markInventoryStrategyStale)
  );

  renderEventFields();
  api("/api/assistant/status").then((runtime) => {
    document.getElementById("assistant-badge").textContent = runtime.enabled ? "OpenClaw" : "not configured";
  }).catch(() => {
    document.getElementById("assistant-badge").textContent = "unavailable";
  });
  runAction("Loading Actual State and process configuration…", loadReference);
  runAction("Loading connected business modules…", loadBusinessModules);
  runAction("Loading CRM service-recovery state…", loadCrm);
}

document.addEventListener("DOMContentLoaded", init);
