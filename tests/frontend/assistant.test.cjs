const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function harness(fetch) {
  function node() {
    return { children: [], value: "", disabled: false,
      appendChild(child) { this.children.push(child); },
      classList: { toggle() {} } };
  }
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, node());
    return elements.get(id);
  };
  const sandbox = vm.createContext({ fetch, console, document: {
    getElementById: get, querySelector: () => get("button"),
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
