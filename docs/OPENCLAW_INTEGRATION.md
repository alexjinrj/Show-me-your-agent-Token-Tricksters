# OpenClaw Agent Runtime Integration

OpenClaw connects to this project through a local Model Context Protocol (MCP)
server. The transport is intentionally outside the business layers:

```text
OpenClaw -> interfaces.mcp -> agent_runtime.ToolRegistry -> tools
```

The MCP process exposes one context-discovery tool and the eleven bounded,
audited sales tools. It does not expose SQL, filesystem, shell, or writable
Actual State access. Scenario tools write only isolated simulation-session and
audit records.

## Prerequisites

- Python 3.12 and `uv`
- A current OpenClaw installation with MCP support (Node 24.16+ or 26.1+;
  Node 26 is recommended by OpenClaw)

Install and verify the Python environment from the repository root:

```bash
uv sync --all-groups
uv run python -m interfaces.mcp.server
```

The second command waits silently for an MCP client on stdin. Stop it with
Ctrl+C when testing manually.

## Register the server with OpenClaw

Use an absolute repository path so OpenClaw can start the server from any
working directory:

```bash
openclaw mcp add sme-business-coordinator \
  --command uv \
  --arg run \
  --arg python \
  --arg -m \
  --arg interfaces.mcp.server \
  --cwd /absolute/path/to/Show-me-your-agent-Token-Tricksters \
  --env BC_DB_PATH=runtime_data/openclaw-enterprise-state.db
```

On Windows PowerShell, enter the command on one line or use backticks for line
continuation. `integrations/openclaw/openclaw.json.example` contains the
equivalent configuration block for manual configuration.

Probe the server before starting an Agent turn:

```bash
openclaw mcp doctor sme-business-coordinator --probe
openclaw mcp tools sme-business-coordinator
```

The probe should list `get_business_context`, five Actual State diagnostics,
and six isolated simulation tools. Start each business conversation with
`get_business_context`; it returns the current base snapshot ID.

## Skill installation

Copy or link `skills/sme-business-coordinator` into an OpenClaw skill root, or
add this repository's `skills` directory to `skills.load.extraDirs`. The skill
instructs the Agent to preserve Actual/Simulated separation and cite tool audit
IDs.

## Security boundary

- All model-provided arguments are validated by strict Pydantic contracts.
- Unknown and extra fields are rejected.
- Every business-tool call is written to `tool_call_audit`.
- The model cannot submit arbitrary SQL or mutate Actual State.
- The MCP process binds no network port; OpenClaw launches it over stdio.
- The generated SQLite database belongs under ignored `runtime_data/`.
