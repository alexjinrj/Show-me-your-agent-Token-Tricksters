const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function harness(fetch) {
  function node() {
    return { children: [], value: "", disabled: false,
      dataset: {}, checked: false, hidden: false, className: "", textContent: "",
      listeners: {}, addEventListener(event, callback) { this.listeners[event] = callback; },
      appendChild(child) { this.children.push(child); },
      classList: { toggle() {}, remove() {} } };
  }
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, node());
    return elements.get(id);
  };
  const sandbox = vm.createContext({ fetch, console, URL, window: {
    location: { hash: "#assistant" }, history: { replaceState() {} },
  }, document: {
    getElementById: get, querySelector: () => get("button"),
    querySelectorAll: () => [],
    createElement: node, addEventListener() {},
  }});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../../frontend/app.js"), "utf8"), sandbox);
  return { sandbox, get, send: () => vm.runInContext("sendChat({preventDefault() {}})", sandbox) };
}

function salesAnalysisResult() {
  const snapshotHash = "a".repeat(64);
  return {
    schema_version: "sales-analysis-result-v1",
    analysis_case: { analysis_case_id: "case-1", snapshot_id: "snapshot-1", snapshot_hash: snapshotHash,
      baseline_run_id: "baseline-1", alternative_run_id: "alternative-1", horizon_days: 7, random_seed: 42 },
    facts: { state_type: "actual", completeness: "current_snapshot_only", snapshot_id: "snapshot-1",
      snapshot_hash: snapshotHash, sales_order_count: 100, backlog_count: 43, backlog_amount_sgd: "250.00" },
    cause_hypothesis: { status: "candidate_not_proven", statement: "Warehouse capacity may contribute." },
    intervention: { owner_domain: "operations", current_value: "0", proposed_value: "2" },
    simulation_comparison: { state_type: "simulated", baseline_run_id: "baseline-1",
      alternative_run_id: "alternative-1", snapshot_hash: snapshotHash, horizon_days: 7, random_seed: 42,
      primary_metric: "average_waiting_hours",
      guardrail_metrics: ["ending_backlog", "fulfilment_rate", "stockout_count"], verdict: "improved",
      metrics: {
        average_waiting_hours: { baseline: "72", alternative: "39", difference: "-33", direction: "lower", materiality_threshold: "1", outcome: "improved" },
        ending_backlog: { baseline: "43", alternative: "43", difference: "0", direction: "lower", materiality_threshold: "1", outcome: "unchanged" },
        fulfilment_rate: { baseline: "0.57", alternative: "0.57", difference: "0", direction: "higher", materiality_threshold: "0.01", outcome: "unchanged" },
        stockout_count: { baseline: "2", alternative: "2", difference: "0", direction: "lower", materiality_threshold: "1", outcome: "unchanged" },
      } },
    actual_state_unchanged: true,
    limitations: ["Current snapshot only"],
  };
}

test("assistant sends stable conversation context and safely renders evidence", async () => {
  const bodies = [];
  const app = harness(async (url, options) => {
    assert.equal(url, "/api/assistant");
    bodies.push(JSON.parse(options.body));
    return { ok: true, json: async () => ({
      reply: "<script>not executable</script>", status: "completed",
      conversation_id: "conversation-1", agent_run_id: "run-1",
      evidence: [{ tool_call_id: "evidence-1", state_type: "actual" }],
    }) };
  });
  for (const message of ["first", "follow-up"]) {
    app.get("chat-input").value = message;
    await app.send();
    assert.equal(app.get("button").disabled, false);
  }
  assert.equal(bodies[0].conversation_id, null);
  assert.equal(bodies[1].conversation_id, "conversation-1");
  assert.equal(bodies[0].session_id, null);
  assert.equal(app.get("assistant-welcome").hidden, true);
  const children = app.get("chat-log").children;
  assert.equal(children[1].textContent, "<script>not executable</script>");
  assert.equal(children[1].dataset.status, "completed");
  assert.match(children[2].children[1].textContent, /evidence-1/);
});

test("assistant starter fills the composer without submitting a request", () => {
  let requestCount = 0;
  const app = harness(async () => { requestCount += 1; });
  vm.runInContext("fillAssistantPrompt('Which inventory items need review?')", app.sandbox);
  assert.equal(app.get("chat-input").value, "Which inventory items need review?");
  assert.equal(requestCount, 0);
});

test("assistant failure unlocks chat and exposes a visible error", async () => {
  const app = harness(async () => ({ ok: false, status: 409, text: async () => "busy" }));
  app.get("chat-input").value = "hello";
  await assert.rejects(app.send(), /409: busy/);
  assert.equal(app.get("button").disabled, false);
  assert.equal(vm.runInContext("state.chatBusy", app.sandbox), false);
  assert.match(app.get("chat-log").children[1].textContent, /Request failed/);
});

test("direct sales analysis sends bounded controls and renders validated evidence", async () => {
  const requests = [];
  const result = salesAnalysisResult();
  const app = harness(async (url, options) => {
    requests.push({ url, body: JSON.parse(options.body) });
    return { ok: true, json: async () => ({ schema_version: "sales-analysis-api-v1", status: "ok",
      tool_call_id: "tool-1", data: result }) };
  });
  app.get("sales-analysis-workers").value = "2";
  app.get("sales-analysis-horizon").value = "7";
  app.get("sales-analysis-seed").value = "42";
  app.get("sales-analysis-primary").value = "average_waiting_hours";
  app.get("sales-guardrail-ending-backlog").checked = true;
  app.get("sales-guardrail-fulfilment-rate").checked = true;
  app.get("sales-guardrail-stockout-count").checked = true;

  await vm.runInContext("runSalesAnalysis({preventDefault() {}})", app.sandbox);

  assert.equal(requests[0].url, "/api/v1/sales/backlog-analysis");
  assert.deepEqual(requests[0].body.guardrail_metrics, ["ending_backlog", "fulfilment_rate", "stockout_count"]);
  assert.equal(app.get("sales-analysis-result").hidden, false);
  assert.match(app.get("sales-analysis-status").textContent, /Actual State was unchanged/);
  assert.equal(vm.runInContext("state.salesAnalysis.toolCallId", app.sandbox), "tool-1");
});

test("sales analysis blocks an inconsistent result contract", async () => {
  const result = salesAnalysisResult();
  result.actual_state_unchanged = false;
  const app = harness(async () => ({ ok: true, json: async () => ({
    schema_version: "sales-analysis-api-v1", status: "ok", data: result,
  }) }));
  app.get("sales-analysis-primary").value = "average_waiting_hours";
  app.get("sales-guardrail-ending-backlog").checked = true;

  await vm.runInContext("runSalesAnalysis({preventDefault() {}})", app.sandbox);

  assert.match(app.get("sales-analysis-status").textContent, /inconsistent evidence/);
  assert.match(app.get("sales-analysis-result").children[0].children[0].textContent, /validation failed/);
});

test("CRM review explicitly carries runtime evidence and resets it for manual selection", async () => {
  const requests = [];
  const option = { id: "refund", label: "Refund", estimatedCost: 10, resolutionDays: 2,
    feasible: true, recommended: true };
  const detail = { id: "CASE-SO74695", issue: "Demo", nextAction: "Review", reasons: [],
    customer: { name: "Anonymous", valueTier: "A", valueScore: 80, riskLevel: "High", riskScore: 70 },
    replyDraft: "Unsent", internalDraft: "Verify",
    investigation: { recommendation: option, options: [option,
      { ...option, id: "reship", recommended: false, feasible: false }],
      rationale: "Derived", boundary: "Unified snapshot; derived order-service cases" } };
  const app = harness(async (url, options) => {
    requests.push({ url, body: options?.body ? JSON.parse(options.body) : null });
    let payload;
    if (url === "/api/assistant") payload = {
      status: "completed", reply: "Review only", agent_run_id: "run-1", conversation_id: "conv-1",
      evidence: [{ status: "ok", tool_name: "recommend_resolution", tool_call_id: "evidence-1",
        data: { result: { complaintId: "CASE-SO74695" } } }],
    };
    else if (url.includes("/complaints/")) payload = { schema_version: "crm-api-v1", data: detail };
    else payload = { schema_version: "crm-api-v1", data: [] };
    return { ok: true, json: async () => payload };
  });
  app.get("chat-input").value = "Investigate CASE-SO74695";
  await app.send();
  assert.equal(requests.length, 1); // No automatic proposal submission by the Agent.
  const trace = app.get("chat-log").children[2];
  await trace.children[2].listeners.click();
  assert.equal(app.get("page-title").textContent, "Customer Relationships");
  assert.equal(app.get("crm-resolution").children[1].disabled, true);
  app.get("crm-resolution").value = "refund";
  await vm.runInContext("submitCrmProposal({preventDefault() {}})", app.sandbox);
  const linked = requests.find((item) => item.url === "/api/v1/crm/proposals" && item.body);
  assert.equal(linked.body.sourceAgentRunId, "run-1");
  assert.equal(linked.body.sourceToolCallId, "evidence-1");
  await vm.runInContext("selectCrmComplaint('CASE-SO74695')", app.sandbox);
  assert.equal(vm.runInContext("state.crmSource", app.sandbox), null);
  assert.ok(!requests.some((item) => item.url.includes("/decision")));
});


test("external evidence links are safe and visibly distinct", async () => {
  const app = harness(async () => ({ ok: true, json: async () => ({
    reply: "Possible event correlation", status: "completed", evidence: [{
      tool_name: "search_public_events", status: "ok", data: {sources: [
        {title: "<img onerror=alert(1)>", url: "https://example.com/source"},
        {title: "Unsafe", url: "javascript:alert(1)"},
      ]},
    }],
  }) }));
  app.get("chat-input").value = "Why did orders rise?";
  await app.send();
  const trace = app.get("chat-log").children[2];
  const link = trace.children[1].children[0];
  assert.equal(link.href, "https://example.com/source");
  assert.equal(link.textContent, "<img onerror=alert(1)>");
  assert.equal(link.rel, "noopener noreferrer");
  assert.equal(trace.children.length, 3); // summary, safe source, raw audit JSON
});

test("inventory candidate filters call the structured endpoint and render Actual State evidence", async () => {
  const requests = [];
  const app = harness(async (url) => {
    requests.push(url);
    return { ok: true, json: async () => ({
      tool_name: "list_inventory_reorder_candidates", status: "ok", state_type: "actual",
      data: { snapshot_id: "snapshot-123", candidate_count: 1, total_recommended_quantity: "8",
        candidates: [{ sku: "SKU-1", name: "Demo", current_stock: "2", reorder_point: "4",
          target_stock: "10", recommended_quantity: "8", risk_level: "critical" }] },
    }) };
  });
  app.get("inventory-risk-level").value = "critical";
  app.get("inventory-top-n").value = "5";
  await vm.runInContext("loadInventoryCandidates({preventDefault() {}})", app.sandbox);
  assert.equal(requests[0], "/api/v1/modules/inventory/reorder-candidates?risk_level=critical&top_n=5");
  assert.match(app.get("inventory-candidate-source").textContent, /Actual snapshot/);
  assert.match(app.get("inventory-candidate-status").textContent, /1 matching candidates/);
  assert.equal(app.get("inventory-refresh-candidates").disabled, false);
});

test("inventory strategy comparison disables duplicate submission and exposes the review boundary", async () => {
  let release;
  let requestCount = 0;
  const response = new Promise((resolve) => { release = resolve; });
  const recommendation = { recommended_strategy: "critical_only", selection_method: "ordered_fallback",
    replenishment_quantity: "10", backlog_reduction: 2, fulfilment_improvement: "0.1",
    gross_profit_improvement: "15", cash_improvement: "-5", actual_state_unchanged: true,
    assumptions: ["Assumption"], limitations: ["Limitation"], baseline_run_id: "base-run",
    recommended_run_id: "recommended-run" };
  const metrics = { ending_backlog: 1, fulfilment_rate: "0.9", stockout_count: 0,
    ending_inventory_quantity: "20", ending_inventory_value: "100", gross_profit: "50",
    ending_cash: "500", minimum_cash: "450", average_waiting_hours: "1", revenue: "80",
    cost_of_goods_sold: "30", accounts_receivable: "5", accounts_payable: "3",
    resource_utilization: {} };
  const runs = ["baseline", "critical_only", "demand_aligned", "full"].map((strategy, index) => ({
    strategy, simulation_run_id: `run-${index}`, result_hash: `hash-${index}`, event_count: index,
    replenishment_quantity: String(index * 10), metrics,
  }));
  const app = harness(async (url) => {
    assert.equal(url, "/api/v1/modules/inventory/strategy-comparison");
    requestCount += 1;
    await response;
    return { ok: true, json: async () => ({ tool_name: "compare_inventory_replenishment_strategies",
      status: "ok", data: { snapshot_id: "snapshot", snapshot_hash: "hash", recommendation,
        strategy_runs: runs, demand_shortages: {} } }) };
  });
  app.get("inventory-horizon-days").value = "30";
  app.get("inventory-effective-day").value = "3";
  app.get("inventory-random-seed").value = "42";
  const first = vm.runInContext("runInventoryStrategyComparison({preventDefault() {}})", app.sandbox);
  const second = vm.runInContext("runInventoryStrategyComparison({preventDefault() {}})", app.sandbox);
  assert.equal(requestCount, 1);
  assert.equal(app.get("inventory-compare-strategies").disabled, true);
  release();
  await Promise.all([first, second]);
  assert.equal(app.get("inventory-compare-strategies").disabled, false);
  assert.equal(app.get("inventory-strategy-results").hidden, false);
  assert.match(app.get("inventory-decision-boundary").textContent, /actual inventory was not changed/i);
  assert.match(app.get("inventory-strategy-status").textContent, /completed/i);
});
