"use strict";

// Business Coordinator demo SPA. Vanilla JS, no build step. All numeric values
// arrive as strings (Decimal) from the API and are displayed verbatim.

const state = {
  sessionId: null,
  events: [],
  processes: [],
  lastRun: null,
  baselineSessionId: null,
  baselineRunId: null,
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

// ---- Assistant chat (Task 10) -----------------------------------------------

function appendChat(role, text) {
  const log = document.getElementById("chat-log");
  const msg = el("div", `chat-message ${role}`, text);
  log.appendChild(msg);
  log.scrollTop = log.scrollHeight;
}

async function sendChat(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message) return;
  appendChat("user", message);
  input.value = "";
  const reply = await api("/api/assistant", {
    method: "POST",
    body: JSON.stringify({
      message,
      session_id: state.sessionId,
      run_id: state.lastRun ? state.lastRun.simulation_run_id : null,
    }),
  });
  appendChat("assistant", `${reply.reply} [${reply.status}]`);
}

// ---- Wiring -----------------------------------------------------------------

function init() {
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
    runAction("Contacting assistant stub…", () => sendChat(event))
  );

  renderEventFields();
  runAction("Loading Actual State and process configuration…", loadReference);
}

document.addEventListener("DOMContentLoaded", init);
