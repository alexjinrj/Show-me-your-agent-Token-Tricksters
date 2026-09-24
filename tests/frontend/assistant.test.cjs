const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function harness(fetch) {
  function node() {
    return { children: [], value: "", disabled: false,
      set innerHTML(value) { if (value === "") this.children = []; },
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
  const children = app.get("chat-log").children;
  assert.equal(children[1].textContent, "<script>not executable</script> [completed]");
  assert.match(children[2].children[1].textContent, /evidence-1/);
});

test("assistant failure unlocks chat and exposes a visible error", async () => {
  const app = harness(async () => ({ ok: false, status: 409, text: async () => "busy" }));
  app.get("chat-input").value = "hello";
  await assert.rejects(app.send(), /409: busy/);
  assert.equal(app.get("button").disabled, false);
  assert.equal(vm.runInContext("state.chatBusy", app.sandbox), false);
  assert.match(app.get("chat-log").children[1].textContent, /Request failed/);
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

test("sales scenario renders matched evidence and rejects inconsistent runs", async () => {
  const requests = [];
  const hash = "a".repeat(64);
  const data = {
    schema_version: "sales-analysis-result-v1",
    analysis_case: { analysis_case_id: "case-1", baseline_run_id: "base-1",
      alternative_run_id: "alt-1", snapshot_hash: hash, horizon_days: 7, random_seed: 42 },
    facts: { state_type: "actual", completeness: "current_snapshot_only", snapshot_id: "snap-1",
      snapshot_hash: hash, sales_order_count: 500, backlog_count: 100,
      backlog_amount_sgd: "482.80", as_of_time: "2026-09-12" },
    cause_hypothesis: { status: "candidate_not_proven", statement: "Possible bottleneck" },
    intervention: { owner_domain: "operations", parameter: "warehouse_staff.capacity_delta",
      current_value: "0", proposed_value: "+2" },
    simulation_comparison: { state_type: "simulated", baseline_run_id: "base-1",
      alternative_run_id: "alt-1", snapshot_hash: hash, horizon_days: 7, random_seed: 42,
      primary_metric: "average_waiting_hours", guardrail_metrics: ["ending_backlog"],
      verdict: "improved", metrics: {
        average_waiting_hours: { baseline: "10", alternative: "8", difference: "-2", outcome: "improved" },
        ending_backlog: { baseline: "100", alternative: "100", difference: "0", outcome: "unchanged" },
      } },
    actual_state_unchanged: true, limitations: ["Model only"],
  };
  const app = harness(async (url, options) => {
    requests.push({ url, body: options?.body ? JSON.parse(options.body) : null });
    return { ok: true, json: async () => url === "/api/assistant/status"
      ? { snapshot_id: "snap-1" }
      : { schema_version: "sales-analysis-api-v1", status: "ok", tool_call_id: "tool-1", data } };
  });
  app.get("sales-workers").value = "2";
  app.get("sales-horizon").value = "7";
  app.get("sales-seed").value = "42";
  await vm.runInContext("runSalesAnalysis({preventDefault() {}})", app.sandbox);
  assert.equal(requests[1].url, "/api/v1/sales/backlog-analysis");
  assert.equal(requests[1].body.snapshot_id, "snap-1");
  assert.equal(requests[1].body.additional_workers, 2);
  const result = app.get("sales-analysis-result");
  assert.ok(result.children.some((node) => node.textContent.includes("Candidate cause")));
  assert.ok(result.children.some((node) => node.textContent.includes("simulated, not executed")));
  assert.ok(result.children.some((node) => node.textContent.includes("Matched comparison: improved")));
  data.simulation_comparison.alternative_run_id = "base-1";
  assert.equal(vm.runInContext("renderSalesAnalysis", app.sandbox)(data), false);
  assert.match(result.children[0].textContent, /contract checks/);
});
