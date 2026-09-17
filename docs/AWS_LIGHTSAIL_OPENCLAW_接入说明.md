# 项目接入 AWS Lightsail OpenClaw 实例：中文操作说明

更新日期：2026-09-17。适用项目：Show-me-your-agent-Token-Tricksters。

本文说明如何连接你已有的 Lightsail OpenClaw 实例，不创建云资源、不修改实例、不上传代码。文中的命令由你在确认目标实例后执行；实例 IP、SSH 用户、密钥路径、OpenClaw 版本和模型配置需要按实际情况替换。

## 1. 先明确接入方式

本项目网页使用 **OpenClaw Gateway 的 HTTP 工具调用接口**，不是把整个 Python 项目放进 OpenClaw 的 workspace，也不是让 OpenClaw 执行 SQL 或 Python 脚本。

```text
用户浏览器
   ↓
项目 FastAPI /api/assistant
   ↓ 携带工具定义与请求上下文
Lightsail OpenClaw Gateway /v1/chat/completions
   ↓ 返回 function tool_calls
项目 ToolExecutor → 销售/库存工具 → 快照与模拟结果
   ↓ 工具证据交回 OpenClaw
最终回答 + 工具证据 + 持久化运行记录 → 浏览器
```

工具和数据库在项目后端所在机器执行；OpenClaw 在 Lightsail 上负责模型推理。目前有 11 个销售工具、2 个库存工具，CRM 尚未接入。模拟不会执行真实采购或修改 Actual State。

建议分两步：

| 阶段 | 项目运行位置 | OpenClaw 运行位置 | 连接方式 |
| --- | --- | --- | --- |
| A：先完成真实联调 | 你的 Windows 电脑 | 已有 Lightsail 实例 | SSH 隧道，最少改动 |
| B：稳定运行 | 同一台 Lightsail 实例 | 同一台 Lightsail 实例 | 主机本地 HTTP，项目用 systemd 托管 |

不要给网页专用 agent 同时注册项目 MCP 服务。网页已通过后端执行工具，重复注册会出现两条不同上下文的业务工具路径。MCP 是另一种独立客户端接入方式，见 [MCP 说明](OPENCLAW_INTEGRATION.md)。

该工具交回方式使用 OpenClaw 官方的 client-function handoff 契约。Gateway 凭证具有高权限，不能交给浏览器。[OpenClaw HTTP 接口说明](https://docs.openclaw.ai/gateway/openai-http-api)

## 2. 准备与版本检查

### 2.1 记录实例信息

在 Lightsail 控制台找到目标实例，记录：

- 实例名称、区域、公网或静态 IP。
- SSH 私钥文件与实际 SSH 用户名。在控制台的 SSH 终端执行 `whoami` 确认，不能一律假设是 `ubuntu`。
- OpenClaw 服务的实际运行用户、配置位置、Gateway 端口和当前模型。
- 当前有效的 Gateway Token。只保存在本地受控环境中，不发到聊天、GitHub、截图或前端代码。

如果是 AWS 官方 OpenClaw 蓝图，先按 Getting started 完成浏览器配对和 AI capabilities 设置。蓝图通常使用 Bedrock；按实例对应的 AWS 引导完成模型权限配置，已有其他可用 provider 则不必重新设置。先在 OpenClaw Dashboard 发一条消息确认模型能正常回答。[AWS 实例入门说明](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-quick-start-guide-openclaw.html)

### 2.2 在实例 SSH 终端检查

以下命令使用 Gateway 实际运行用户执行。不要随意在前面加 `sudo openclaw`，否则可能读取 root 的另一套配置。

```bash
whoami
openclaw --version
node --version
openclaw gateway status
openclaw agents list
openclaw config --help
```

当前 CLI 支持时，再执行：

```bash
openclaw config file
openclaw config schema
```

`config file` 是 CLI 解析的配置路径；还应确认运行中的服务没有使用另一个 profile、`OPENCLAW_CONFIG_PATH` 或服务环境变量。若服务与 CLI 不一致，先解决配置位置问题。[配置 CLI 文档](https://docs.openclaw.ai/cli/config)

本项目至少需要 Gateway 支持：

- `POST /v1/chat/completions`。
- 请求中的 `tools`、结构化 `message.tool_calls`。
- 后续请求中的 `role: tool` 和匹配的 `tool_call_id`。
- `openclaw/<agent_id>` 指定专用 agent。

“Dashboard 能聊天”不等于以上协议都支持。当前官方 agent 配置使用 `agents.entries`；旧镜像可能使用 `agents.list`。遇到 schema 不匹配，不要把新示例硬塞进旧配置，也不要退回一个普通文本接口冒充工具调用。

需要升级时，先建立 Lightsail 实例快照，并备份有效配置及认证状态；按该安装方式的官方升级流程处理。升级可能改变 Node 要求或 AWS 镜像集成，不能在未检查兼容性时直接全局重装。[当前 agent 配置参考](https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent)

## 3. 配置实例上的 OpenClaw

### 3.1 备份并保留现有设置

先用 `openclaw config file` 确认路径。将配置复制为带日期的备份，备份同样包含秘密，需要严格限制权限。保存好原有模型、provider、Bedrock/IAM 设置、auth、channels 和 Dashboard 入口配置。

不要用仓库示例覆盖整个 `openclaw.json`；只合并需要的字段。

### 3.2 开启 HTTP 接口

在支持该字段的版本中执行：

```bash
openclaw config set gateway.http.endpoints.chatCompletions.enabled true
```

本项目会在 `BC_OPENCLAW_URL` 后自动追加 `/v1/chat/completions`，因此后端变量只填写 Gateway 的根地址，不附加 `/v1` 或接口路径。

### 3.3 创建专用业务 agent

确认尚不存在同名 agent 后，使用当前版本支持的 CLI 创建：

```bash
openclaw agents add business-coordinator --workspace "$HOME/.openclaw/workspace-business-coordinator"
```

按向导确认该 agent 的模型/provider 可用。不同版本和认证方式的继承行为不同，不要仅因为默认 agent 正常就认定新 agent 一定能调用模型。[agents CLI 文档](https://docs.openclaw.ai/cli/agents)

在当前 `agents.entries` schema 下，将以下字段合并到该 agent 已有条目，保留向导建立的 workspace、agentDir、model 等内容：

```json
{
  "agents": {
    "entries": {
      "business-coordinator": {
        "skills": [],
        "tools": {
          "profile": "minimal",
          "deny": [
            "group:fs",
            "group:runtime",
            "group:openclaw",
            "group:plugins",
            "canvas"
          ],
          "elevated": { "enabled": false }
        }
      }
    }
  }
}
```

这里关闭 OpenClaw 内部的文件、命令、插件等能力；业务函数由 HTTP 请求提供，再由项目后端验证和执行。具体配置必须通过实例版本的 schema，最后还要用真实工具调用验收。[工具策略参考](https://docs.openclaw.ai/gateway/config-tools/tool-policy)

仓库中也有 [Gateway 配置示例](../integrations/openclaw/gateway.json.example)。其中 `gateway.bind: loopback` 适用于私有入口；AWS 镜像可能已有 Dashboard 反向代理。先确认代理连接方式，再决定是否修改 bind，避免把原有 Dashboard 弄断。无论 Dashboard 怎样开放，都不能把新启用的 Chat Completions 高权限接口直接开放给公网。

### 3.4 校验并重启原有 Gateway 服务

当前版本支持时执行：

```bash
openclaw config validate
openclaw gateway restart
openclaw gateway status
```

若 AWS 镜像使用系统级 `openclaw-gateway` 服务，而 CLI 的重启命令没有管理该服务，应确认服务名称后使用原有服务管理方式。例如旧镜像可使用 `sudo systemctl restart openclaw-gateway`。不要另外启动第二个 Gateway 占用同一端口。

检查实际监听地址与端口；下面假设是 18789：

```bash
ss -lnt | grep ':18789'
```

如果使用别的端口，后面的隧道和后端地址都要一起调整。

## 4. 方案 A：本地项目连接云端 OpenClaw

这是建议先完成的路径。无需先把项目、数据库或 Python 环境搬到 AWS。

### 4.1 限制网络入口

在 Lightsail Networking 中，SSH 22 端口尽量只允许你的公网 IP。若使用控制台浏览器 SSH，保留它所需的访问设置。

本方案不需要向公网开放 18789 或 8000。也要检查已有 Dashboard 的反向代理，确保它不会把 `/v1/chat/completions` 一并对公网转发。SSH 方式可直接转发远程主机回环端口。[OpenClaw 远程连接说明](https://docs.openclaw.ai/gateway/remote)

### 4.2 Windows 终端 A：建立 SSH 隧道

先替换下面三处：私钥文件、SSH 用户名、实例 IP。首次连接核对主机指纹，不要禁用主机身份检查。

```powershell
ssh -i 'C:\Users\21945\Downloads\LightsailKey.pem' -N -L 127.0.0.1:18790:127.0.0.1:18789 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 SSH_USER@INSTANCE_IP
```

保持终端 A 开着。执行后没有输出、终端不退出通常是正常的。这里本地使用 18790，避免与你电脑上其他 Gateway 的 18789 冲突。

此时电脑上的 `http://127.0.0.1:18790` 通向实例上的 Gateway。公网 IP 只出现在 SSH 连接中，不是项目的 Gateway URL。

### 4.3 Windows 终端 B：配置后端环境

在本地项目根目录执行：

```powershell
Set-Location 'C:\Users\21945\Desktop\NUS\hackthon\Show-me-your-agent-Token-Tricksters-git'
$env:BC_OPENCLAW_URL = 'http://127.0.0.1:18790'
$env:BC_OPENCLAW_AGENT_ID = 'business-coordinator'
$gatewaySecret = Read-Host '输入当前 Gateway Token' -AsSecureString
$env:BC_OPENCLAW_TOKEN = [System.Net.NetworkCredential]::new('', $gatewaySecret).Password
```

本项目的 `.env.example` 只是说明，不会自动读取 `.env`。变量必须进入启动后端的进程环境。Gateway Token 不是模型 API Key、AWS Access Key 或 SSH 私钥；Bedrock/provider 认证由云端 OpenClaw 管理。

### 4.4 先单独验证云端 Gateway

在终端 B 执行，确认 Bearer 认证、HTTP 路径及 agent/model 都可用：

```powershell
$probe = @{
  model = 'openclaw/business-coordinator'
  messages = @(@{ role = 'user'; content = '请只回复：连接成功' })
  max_completion_tokens = 64
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$env:BC_OPENCLAW_URL/v1/chat/completions" -Method Post -Headers @{ Authorization = "Bearer $env:BC_OPENCLAW_TOKEN" } -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($probe))
```

成功响应应包含 `choices` 和 assistant 消息。这里只验证文本与认证；真正的工具协议必须继续通过第 6 节验收。

不要使用 `http://INSTANCE_IP:18789`：本项目拒绝非回环地址的明文 HTTP。SSH 隧道兼顾加密和当前客户端兼容性。未来如走 HTTPS，应使用有效证书、私有访问控制和直接根地址；当前客户端不跟随重定向。[HTTP 接口安全边界](https://docs.openclaw.ai/gateway/openai-http-api)

### 4.5 启动项目

本机已经有本项目的 `.venv` 时：

```powershell
& '.\.venv\Scripts\python.exe' -m uvicorn interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

新环境需要先安装 Python 3.12 和 uv，再执行 `uv sync --frozen --all-groups --python 3.12`，然后可使用同样的启动命令。项目要求 Python 3.12，不能直接使用系统 Python 3.13。

打开 `http://127.0.0.1:8000`。手机或队友不能直接访问你电脑的 `127.0.0.1`，这是当前私有联调方案的预期行为。

## 5. 方案 B：把项目后端部署到同一台 Lightsail

完成方案 A 后，再进行这一节。项目进程和 Gateway 都在实例主机上运行，后端地址变为 `http://127.0.0.1:18789`。浏览器仍然不直接访问 Gateway。

### 5.1 确保部署的是完整 Runtime 代码

最新 Sales/Inventory Runtime 代码与交接文档发布在 `feature/agent-runtime` 分支，尚未合并到 `main`。实例部署时明确选择该分支，并记录 `git rev-parse HEAD` 输出的提交号；不要默认克隆 `main` 后就认为拿到了完整 Runtime 链路。

可以克隆该分支，或将经过验证的提交打包传输。不要提交或打包 `.env`、Token、私钥或现有数据库。注意 `git archive HEAD` 只包含已提交文件，不包含本地未提交修改。

部署包至少包含：`pyproject.toml`、`uv.lock`、`src/`、`frontend/`、`data/load_data/`、`scripts/smoke_agent_runtime.py`、`migrations/`、`alembic.ini`、`integrations/openclaw/`。容器部署还要带上 `Dockerfile` 和 `.dockerignore`；文档可一并传输。排除 `.venv/`、`.deps/`、`.git/`、`.env`、私钥、缓存和 `runtime_data/` 中的现有数据库；不要直接搬 Windows 虚拟环境到 Linux。

在实例中用一个新的部署目录，例如 `/home/SSH_USER/sme-runtime`，不要覆盖 OpenClaw 的安装目录或已有 workspace。进入目录后确认至少存在：

```bash
ls src/agent_runtime/service.py
ls src/interfaces/runtime.py
ls scripts/smoke_agent_runtime.py
```

### 5.2 建立 Python 环境

在实例项目目录中，用你安装好的 uv 执行：

```bash
uv python install 3.12
uv sync --frozen --no-dev --python 3.12
mkdir -p runtime_data
```

缺少 uv 时，按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/) 安装到部署用户环境；先核对发行版和现有工具，不要猜测所有 Lightsail 蓝图都支持相同的包管理命令。

项目启动时会播种演示 CSV 并创建缺失表。这里部署的是演示数据，不代表已经接入真实 ERP。

若使用已有数据库，先停项目服务并做一致性备份，再迁移。`alembic.ini` 默认指向 `actual_state.db`，不会自动根据 `BC_DB_PATH` 改目标；必须确认迁移配置指向实际使用的同一数据库，不能盲目执行 `alembic upgrade head`。详细表变化见 [Runtime 交接文档](AGENT_RUNTIME_HANDOFF.md)。

### 5.3 保存服务器端环境变量

为该项目建立独立的环境文件，不修改 OpenClaw 自己的服务环境：

```bash
sudo touch /etc/sme-runtime.env
sudo chmod 600 /etc/sme-runtime.env
sudoedit /etc/sme-runtime.env
```

写入以下内容，替换用户目录和 Token：

```ini
BC_OPENCLAW_URL=http://127.0.0.1:18789
BC_OPENCLAW_AGENT_ID=business-coordinator
BC_OPENCLAW_TOKEN=REPLACE_WITH_CURRENT_GATEWAY_TOKEN
BC_DB_PATH=/home/SSH_USER/sme-runtime/runtime_data/enterprise_state.db
BC_DEMO_DATA_DIR=/home/SSH_USER/sme-runtime/data/load_data/adventureworks_demo
BC_CONFIG_DIR=/home/SSH_USER/sme-runtime/src/core/process_definitions
BC_WEB_DIR=/home/SSH_USER/sme-runtime/frontend
```

这是 systemd 的 EnvironmentFile，行首不要写 `export`，路径必须是实际绝对路径。文件中 Token 应为有效单行值，不要保留占位符。不要把该文件加入仓库。

### 5.4 用 systemd 托管后端

确认实例使用 systemd。编辑 `/etc/systemd/system/sme-runtime.service`，替换 `SSH_USER`：

```ini
[Unit]
Description=SME Business Coordinator Runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=SSH_USER
WorkingDirectory=/home/SSH_USER/sme-runtime
EnvironmentFile=/etc/sme-runtime.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/SSH_USER/sme-runtime/.venv/bin/python -m uvicorn interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
TimeoutStopSec=300
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

保存后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sme-runtime
sudo systemctl status sme-runtime --no-pager
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/api/assistant/status
```

必须先保证原有 Gateway 服务已经健康。这里不硬编码它的 systemd 单元名，因为 AWS 镜像可能用系统服务或用户服务。

保持 `--workers 1`：当前 Runtime 使用进程内锁协调 SQLite 与会话，不具备多 worker 的分布式并发控制。

### 5.5 从电脑访问实例上的网页

Windows 上新开 SSH 隧道：

```powershell
ssh -i 'C:\Users\21945\Downloads\LightsailKey.pem' -N -L 127.0.0.1:18000:127.0.0.1:8000 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 SSH_USER@INSTANCE_IP
```

浏览器打开 `http://127.0.0.1:18000`，本方案不用开放公网 8000。

若需要团队公网演示，必须另加 HTTPS 和用户认证/访问限制后再发布，例如在已有代理中配置独立项目入口。当前 API 没有用户认证，直接开放会暴露业务数据、运行记录及消耗模型额度的分析接口。代理等待时间要覆盖长分析请求，例如 310 秒，并确认 Gateway 路由不会随项目入口一起被公开。

### 5.6 如果一定要使用现有 Dockerfile

先完成主机进程部署验收。当前镜像可以运行 API，但文中验收脚本没有被 Dockerfile 复制进去，不能直接假设容器内存在 `scripts/smoke_agent_runtime.py`。

同一台 Linux 实例上的容器，`127.0.0.1` 默认指容器自己，不是主机 Gateway。针对这个演示，可选择 Linux 主机网络模式：

```bash
docker build -t sme-runtime:local .
docker volume create sme-runtime-data
```

另外建立权限 600 的 Docker 环境文件，只放三个 `BC_OPENCLAW_*` 值，Gateway URL 为 `http://127.0.0.1:18789`。确认没有同名容器、没有其他项目占用 8000 后：

```bash
docker run -d --name sme-runtime --restart unless-stopped --network host --env-file /ABSOLUTE/PATH/sme-runtime-docker.env -e BC_HOST_PORT=8000 -v sme-runtime-data:/data sme-runtime:local /opt/venv/bin/python -m uvicorn interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

这里主动覆盖镜像默认的全接口监听，保持 API 私有；主机网络模式下不需要 `-p`。卷内数据库沿用镜像默认 `/data/demo_actual_state.db`，不要把第 5.3 节的主机数据库路径原样套进容器。

不要把 URL 换成明文 `http://host.docker.internal:18789` 来绕过问题：当前客户端会拒绝非回环 HTTP。以上仅适用于 Linux 主机，不是 Windows Docker Desktop 的部署步骤。主机部署与容器部署二选一，不要同时占用同一 8000 端口。

## 6. 验收：不能只看 enabled=true

`/healthz` 只说明 API 活着；`/api/assistant/status` 中 `enabled=true` 只说明 URL 和 Token 已配置，不证明连接、认证、模型或工具协议正常。

方案 A 在本地另开终端执行：

```powershell
Set-Location 'C:\Users\21945\Desktop\NUS\hackthon\Show-me-your-agent-Token-Tricksters-git'
& '.\.venv\Scripts\python.exe' scripts/smoke_agent_runtime.py --api-url http://127.0.0.1:8000
```

方案 B 在实例项目目录执行：

```bash
.venv/bin/python scripts/smoke_agent_runtime.py --api-url http://127.0.0.1:8000
```

容器部署也可在电脑通过 18000 隧道运行本地脚本，`--api-url` 使用 `http://127.0.0.1:18000`。

脚本会发出真实模型请求，并创建分析、审计及模拟记录，有 provider 调用费用；不会执行真实采购。它验证：

1. 销售汇总和库存补货候选工具确实被调用。
2. 库存四策略模拟工具确实被调用。
3. 请求得到 `completed`，工具结果均为 `ok`。
4. 回传运行记录可再次查询，且内容一致。
5. 分析前后基准快照 hash 未变化。

成功输出包含两次 `PASS <agent_run_id>` 和最后的 `PASS live OpenClaw chain and immutable snapshot`。失败时保留 agent_run_id，查询 `/api/assistant/runs/<agent_run_id>` 检查工具证据；不要把含业务数据或秘密的完整日志公开。

再到网页手动验证销售“创建基线 → 运行 → 分叉 → 增加仓库人员 → 运行替代方案 → 比较”，要求相同快照、horizon 和 seed。回答应该区分 Actual 与 Simulated，引用证据 ID，不能声称已执行采购。

此前 107 项 Python 测试和 2 项前端测试使用模拟 Gateway/真实业务工具等方式验证代码，不等于你的 Lightsail 实例已通过真实联调。

## 7. Token 轮换、维护和备份

AWS 官方说明：MOTD 2.0.0 镜像有每日自动 Token 轮换，旧版本管理方式不同。先看 SSH 欢迎信息确认镜像行为。不要为省事关闭轮换或关闭 Gateway 认证。[AWS 镜像版本与 Token 说明](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-quick-start-guide-openclaw.html)

Token 变化后：

- 本地方案：更新终端 B 的 `BC_OPENCLAW_TOKEN`，然后重启项目后端。只改另一个终端的变量不会影响运行中的进程。
- systemd 方案：安全更新 `/etc/sme-runtime.env`，执行 `sudo systemctl restart sme-runtime`，再次验收。
- Docker 方案：更新受控环境文件后重新创建容器，保持原数据卷；单纯 `docker restart` 不会重新载入 `--env-file`。重建前先确认旧容器和卷的准确名称，不能删除持久化卷。

当前客户端启动时读取 Token，没有自动追踪 AWS 轮换。需要长期无人值守时，应另行设计受控的凭证同步/重载流程；本文不提供读取欢迎信息的脆弱抓取脚本。

日志入口：

```bash
sudo journalctl -u sme-runtime -n 100 --no-pager
```

备份应包括项目使用的 SQLite、部署版本、服务配置，以及单独保护的 OpenClaw 配置/认证资料。SQLite 在写入期间不要只随意复制一个 `.db` 文件；停项目后备份，或使用 SQLite 一致性备份机制。恢复/升级前先验证备份，避免覆盖唯一的有效数据库。

模型调用费用与 Lightsail 实例费用分开关注。`model_usage` 只记录 Gateway 报告的用量，不是账单；缺失用量不会被项目猜测补齐。

## 8. 常见故障

| 现象 | 排查方向 |
| --- | --- |
| SSH 超时 | IP、密钥、用户名、Lightsail SSH 规则、本机公网 IP 是否变化 |
| 隧道显示端口占用 | 换一个本地端口，并同步修改 URL；不要结束不相关服务 |
| enabled=false / disabled | 环境变量没有进入后端进程，或只改了 `.env`；检查 systemd EnvironmentFile |
| Gateway HTTP 401/403 | Token 已轮换、用错 Token 或实际 auth 模式不兼容；当前客户端只发送 Bearer Token |
| Dashboard 正常，HTTP 404 | HTTP endpoint 未开启、访问了 Dashboard 代理路径而非 Gateway、或旧版本不支持 |
| invalid Gateway response / 不返回 tool_calls | 镜像不支持 client-function handoff、模型不支持工具调用，或 agent 策略/配置不正确 |
| 模型权限/调用错误 | 专用 agent 的 provider、Bedrock 权限、模型访问条件及区域配置 |
| Non-loopback Gateway requires HTTPS | 填了实例公网/私网明文 HTTP 或容器宿主别名；改用 SSH/同机回环/受保护 HTTPS |
| Gateway redirects are not permitted | URL 指向会跳转的 Dashboard、登录页或代理；使用可直接 POST 的根地址 |
| Runtime HTTP 409 | 已有分析请求正在运行，或 session/run 上下文不匹配；等待或传入正确 ID |
| 60 秒附近 Gateway 超时 | 模型延迟、provider 网络或额度；代理加长超时不能改变客户端 60 秒限制 |
| Tool-call / reasoning-round budget exhausted | 任务过大或工具循环，缩小问题；默认 8 轮、16 次工具调用 |
| 数据库只读或路径不存在 | 部署用户写权限、绝对路径、容器持久化卷及 BC_DB_PATH 是否一致 |
| 重启后 401 | 优先核对 AWS Token 轮换，而不是直接放开工具执行权限 |

当前 API 是可信单公司、单进程演示服务，没有多租户权限、真实交易审批执行、自动任务恢复或流式任务队列。不要为了“能连上”修改为 `tools.exec.security=full`、关闭询问、禁用认证或把项目/Gateway 端口全开放。

## 9. 最短操作顺序

1. 在 Lightsail Dashboard 确认模型正常，检查实例 OpenClaw 的版本和工具协议。
2. 备份；开启 Chat Completions；建立并限制 `business-coordinator` agent；校验并重启原服务。
3. 电脑建立到 Gateway 的 SSH 隧道，后端设置三个 `BC_OPENCLAW_*` 变量。
4. 单独验证 HTTP 认证，启动本地网页，执行真实 smoke 验收。
5. 再把完整 Runtime 代码部署到同一实例，用单 worker 服务和持久化数据库运行。
6. 保持私有入口；明确 Token 轮换后的更新与后端重启流程。

这六步完成且真实验收通过，才算项目真正接入该 Lightsail OpenClaw 实例。
