# 在 NSCC 测试销售 Agent

本项目只需 CPU。无需在 NSCC 上启动浏览器或公开端口：PBS 作业完成后生成离线 `sales_report/index.html`，下载到本机打开即可。

## 1. 登录并确认项目目录

按你获批的集群选择登录入口；NUS 用户的 ASPIRE2A 与 ASPIRE2A+ 主机名不同，校外通常需要先连接 NUS VPN。登录后切到**含有 `pyproject.toml`、`scripts/`、`data/load_data/adventureworks_demo/` 的项目根目录**。上传时不要只传 `src/`；演示数据和脚本也必须在同一项目中。

```bash
cd /path/to/Show-me-your-agent-Token-Tricksters-main
ls pyproject.toml scripts/nscc_sales_test.pbs data/load_data/adventureworks_demo/sales_orders.csv
```

官方入口：[ASPIRE2A FAQ](https://help.nscc.sg/aspire2a/faqs/)；[ASPIRE2A+ FAQ](https://help.nscc.sg/aspire2aplus/faqs/)。

## 2. 建立 Python 3.12 环境，不需要 uv

在登录节点进行一次环境安装。先用 `module avail miniforge3` 确认模块名称；下面的 `module load miniforge3` 是 NSCC ASPIRE2A 文档给出的命令，若你在 ASPIRE2A+ 上看到不同模块名，以 `module avail` 为准。

```bash
module avail miniforge3
module load miniforge3
conda create -y -p "$PWD/.conda-sales" python=3.12 pip
"$PWD/.conda-sales/bin/python" -m pip install -e . pytest ruff mypy types-PyYAML
"$PWD/.conda-sales/bin/python" --version
```

最后一行应显示 Python 3.12。`pip install -e .` 读取项目的运行依赖；后四个包用于测试和检查。无需 GPU，也无需 OpenAI API Key，因为该演示验证的是确定性 Sales Tools 与 Skills 的证据链。NSCC 的 [Miniforge 说明](https://help.nscc.sg/aspire2a/faqs/)允许用户自建环境。

## 3. 提交 CPU 测试作业

在项目根目录提交，替换为你获批的 NSCC Project ID：

```bash
qsub -P YOUR_PROJECT_ID scripts/nscc_sales_test.pbs
qstat -u "$USER"
```

作业脚本请求单节点、2 CPU、4 GB 内存、20 分钟，依次运行测试、导入 demo 数据并生成报告。若你的项目使用不同队列，请按该集群/项目的 PBS 队列要求修改脚本中的 `#PBS -q normal`。NSCC 使用 PBS `qsub`/`qstat`；参见 [ASPIRE2A 快速指南](https://help.nscc.sg/wp-content/uploads/2024/06/ASPIRE2A-General-Quickstart-Guide-1.pdf)及 [ASPIRE2A+ 指南](https://help.nscc.sg/wp-content/uploads/ASPIRE2A_Plus_General_Quick_Start_Guide.pdf)。

作业完成后，检查 PBS 输出日志中是否显示 `29 passed` 和 `Visual report:`。结果文件位于：

```text
sales_report/index.html
sales_report/demo.json
```

## 4. 下载并可视化验收

用 WinSCP/FileZilla 从 NSCC 下载 `sales_report/index.html`；也可从本机 PowerShell 使用 `scp`（替换用户名、登录主机和 NSCC 上的绝对路径）：

```powershell
scp USER@LOGIN_HOST:/absolute/path/to/project/sales_report/index.html .
```

双击本机的 `index.html`。在当前主分支的流程定义中，报告应显示：100 条当前积压位于 `allocate_inventory` 节点、情景比较、run ID，以及证据限制提示。HTML 不加载外部脚本或数据，单文件即可离线查看。若要逐项核对数字，打开 `demo.json`。

注意：`sales_demo.db` 和 `sales_report/` 是演示产物；重新运行会追加新的会话/审计记录，但相同快照、事件、期限与随机种子的仿真结果哈希应保持一致。样例的等待时间可改善，期末积压不一定减少；只按报告中的实际结果解释。

## 5. 用 LLM 输入问题并查看 Agent 轨迹

上传新增的 `scripts/chat_sales_agent.py` 和 `src/agent_runtime/llm_runner.py`，保留已生成的 `sales_demo.db`。此入口直接调用现有销售工具，不需要额外安装 LLM SDK。你需要一个支持 Chat Completions 函数调用的 API、模型名和密钥；在 NSCC 可访问该 API 的计算节点上运行。不要把密钥写进脚本、PBS 文件或版本库。

先在计算节点申请交互任务（把 Project ID 改成自己的）：

```bash
qsub -I -P YOUR_PROJECT_ID -q qdev -l select=1:ncpus=1:mem=2gb -l walltime=00:20:00
cd /home/users/nus/yangyanh/hackthon/Show-me-your-agent-Token-Tricksters-main
```

在项目根目录把 `.env.example` 复制成 `.env`，然后填写 API 信息。`SALES_LLM_BASE_URL` 填服务商的 **API 根路径**，例如以 `/v1` 结尾，不要再加 `/chat/completions`。未设置时使用 OpenAI 官方地址。`SALES_LLM_MODEL` 必须填写服务商实际提供、支持工具调用的模型名。

```bash
cp .env.example .env
chmod 600 .env
vi .env
set -a
source .env
set +a
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py \
  --database sales_demo.db \
  --mode exceptions \
  --prompt '当前销售订单积压多少？主要在哪个流程节点？请给出证据。'
```

`.env` 已被 Git 忽略，不会随正常的 `git add` 提交；不要上传或分享包含真实密钥的文件。每次重新登录 NSCC 或开启新的 PBS/交互任务，都要在项目根目录重新执行 `set -a; source .env; set +a`。脚本仍只读取进程环境变量，因此不需要安装 `python-dotenv`。

终端会逐轮显示 Agent 的工具选择、参数、工具结果、最终回答和 API 返回的 token 用量。结束后，下载 `sales_report/llm_trace.html` 到本机双击查看逐步轨迹；`sales_report/llm_trace.json` 保存完整结构化记录。两者不会覆盖之前的 `index.html` 和 `demo.json`。

测试情景分析时，可使用：

```bash
"$PWD/.conda-sales/bin/python" scripts/chat_sales_agent.py \
  --database sales_demo.db \
  --mode scenario \
  --prompt '如果仓库增加一名员工，30 天内平均等待时间与积压相比基线如何变化？'
```

默认最多 8 轮模型响应、12 次工具调用，每轮输出上限 600 token。若模型因输出上限无法完成，可增加 `--max-output-tokens 1000`；若兼容服务商只接受 `max_tokens`，追加 `--token-param max_tokens`。这些限制控制单次验证成本，不代表精确的费用上限。`--mode auto` 会按提问关键词选工具集；遇到误判请显式指定 `exceptions` 或 `scenario`。

更多只针对销售订单概览、积压构成、订单追踪、证据、历史缺失和职责边界的 prompt 与验收条件，见 `docs/SALES_LLM_EVAL_CASES.md`。
