# AgentHarness

AgentHarness 是一个本地运行、由 Human Supervisor 监督的多 Agent 研发工作流控制台。项目目标是把“需求 -> 计划 -> 开发 -> [ 评审 -> 修复 -> 复审 ] -> 验收 -> 归档”的研发链路产品化，让 Codex、Claude 等本地 Agent 在可观测、可追溯、可人工介入的流程中协作。

当前版本不直接调用 OpenAI、Claude 或 DeepSeek 云端 API，而是通过本机 Codex App Server 和 Claude CLI 接入受控 worker；Gemini 作为系统内部秘书能力，通过受控后端服务调用 Gemini 原生 API。AgentHarness 负责流程编排、状态机、提示词构建、证据保存、人类门禁和前端操作台；真正的代码生成和评审动作发生在用户选择的业务项目 workspace 中。

## 当前架构

- 后端：Python 3.11、FastAPI、SQLModel、MySQL、asyncio。
- 前端：Vue 3、Vite、Element Plus、Pinia。
- 测试数据库：后端测试使用 SQLite，不依赖 MySQL。
- 运行数据库：MySQL。
- 本地 Agent 接入：Codex App Server、Claude CLI。
- 系统内部 AI：Gemini，通过后端调用 Gemini 原生 API。

当前真正作为 AgentWorker 登记的只有三个：

- `Codex`：生成计划、执行开发、修复问题、生成验收建议、维护 `README.md` 归档文档。
- `Claude`：执行代码评审和复审，并维护被评审业务项目的 `REVIEW.md`。
- `Gemini`：第三个 agent，当前定位为 AgentHarness 的“秘书”，负责使用提醒、进度摘要、门禁提示、任务事实问答和安全流程推进建议。它不能替代 Human Supervisor 批准计划、依赖、验收或高风险修复。

## 设计特点

AgentHarness 的核心设计是把 agent 能力放进一个可控流程，而不是让 agent 直接接管仓库。

系统通过状态机约束每一步可以发生的动作，通过 AgentRun 保存输入、输出、诊断和执行状态，通过 Human Supervisor 门禁保留计划确认和最终验收等关键决策。

在实现上，AgentHarness 采用控制面 / 数据面分离：本仓库保存任务、状态、提示词和运行证据；Codex / Claude 在用户选择的外部业务项目 `workspace_path` 中完成具体开发和评审。前端的 Agent Prompt 面板会展示将发送给 agent 的完整提示词，并允许用户在匹配当前 run type 时手动调整后重新运行。

Accept 阶段不会直接让用户点“验收通过”。系统会先要求 Codex 生成面向人类的验收建议，例如页面操作、API 调用、命令验证、日志检查和通过/打回标准，再由 Human Supervisor 做最终决定。Archive 阶段则由 Codex 维护 `README.md`，让文档记录项目当前事实，而不是沉淀任务流水账。

## Agent 接入状态

### Codex App Server

Codex 通过 App Server 方式接入：

```text
codex app-server --listen ws://127.0.0.1:<port>
```

后端负责：

- 为每次运行启动本地 App Server。
- 创建或复用同一任务的 Codex thread。
- 在任务 `workspace_path` 下启动 turn。
- 为不同 run type 选择合适的提示词和运行模式。
- 保存 thread id、turn id、输入、输出、诊断信息和执行状态。

当前 Codex run type：

- `codex_plan`
- `codex_implement`
- `codex_fix`
- `codex_acceptance_checklist`
- `codex_archive`

其中 `codex_plan` 和 `codex_acceptance_checklist` 按只读 Codex run 处理；implement、fix、archive 根据提示词允许在 workspace 中写入。

### Claude CLI

Claude 通过非交互 CLI 方式接入：

```text
claude -p --output-format json --permission-mode acceptEdits
```

当前限制工具为：

```text
Read, Edit, MultiEdit, Glob, Grep
```

并禁用：

```text
Bash
```

后端负责：

- 在任务 `workspace_path` 下启动 Claude。
- 从 JSON 输出中解析 `session_id`、`uuid`、结果文本和诊断信息。
- Review / Recheck 复用同一任务的 `session`。
- 同一 workspace 下活跃` session `大约每 5 个不同任务轮换一次。
- 将 Claude 的评审结论展示在 Agent Runs 中，并把权限、退出原因、模型使用等信息放入 Diagnostics。

当前 Claude run type：

- `claude_review`
- `claude_recheck`
- `claude_finalize`

三种运行职责彼此分离：

- `claude_review`：进行首次代码审查并维护问题清单，不执行封板。
- `claude_recheck`：仅验证 Codex 对开放问题的修复结果，不执行封板。
- `claude_finalize`：不重新进行全面代码审查；确认没有未关闭问题、校验 REVIEW.md 状态一致性并执行最终封板归档。

### Gemini API

Gemini 作为系统内部 Secretary agent 接入，不在外部业务项目 `workspace_path` 中执行命令，也不直接修改业务代码。后端通过 Gemini 原生 API 调用模型：

```text
models/{model}:generateContent
models/{model}:streamGenerateContent?alt=sse
```

推荐环境变量：

```env
GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com
GEMINI_PROXY_URL=http://127.0.0.1:7890
```

后端负责：

- 从任务状态、事件、AgentRun、Review 结果、CommandRun、gate 和允许流转中构建只读 task facts。
- 通过一次只读任务快照复用 Task、当前轮 AgentRun、Review、近期事件和命令结果，避免工作流解析与 Gemini facts 重复查询。
- 为任务 brief 和任务对话构建同一套面向用户的精简上下文，不向 Gemini 暴露无关的工作区路径、provider 字段和内部状态枚举。
- 使用 `facts_version` 标识事实层版本，供前端缓存和判断 Gemini brief 是否过期。
- 调用 `generateContent` 生成结构化任务简报。
- 调用 `streamGenerateContent?alt=sse` 提供 Gemini 对话流式回复。
- 将 Gemini 限定为 Secretary Mode：只做总结、解释、问答、风险提示和下一步建议。

当前 Gemini 能力：

- 首页 Gemini 对话框：展示固定问候，并支持普通秘书式问答。
- 任务详情 Gemini 对话框：基于当前任务 facts 回答进度、gate、风险和下一步问题。
- 任务 brief：在 `PLAN_READY`、`IMPLEMENT_DONE`、`REVIEW_DONE`、`RECHECK_DONE`、`ACCEPTANCE_READY`、`ACCEPTANCE_PASSED`、`ARCHIVED` 和 `DONE` 等关键状态后台预热，并基于 `facts_version` 缓存；即使弹窗未打开，也会执行预热。
- Gemini 对话仅保存在当前前端会话内；关闭弹窗或点击弹窗刷新按钮时，会清空当前页面作用域下的用户与 Gemini 对话。
- SSE 流式输出：后端转发 Gemini 原生 stream delta，前端实时刷新消息气泡。

当前 Gemini 不能：

- 不能确认计划。
- 不能批准验收。
- 不能安装依赖。
- 不能绕过 Human Supervisor gate。
- 不能直接触发 worker run 或修改任务状态。
- 不能直接修改外部业务项目代码。

## Worker 状态与心跳

三个 Agent 使用统一的 Worker 状态：

- `ONLINE`：provider 已配置且当前空闲。
- `RUNNING`：当前存在活动任务或 API 请求。
- `FAILED`：最近一次运行、连接或 API 调用失败。
- `OFFLINE`：provider 未配置、对应命令不存在或无法启动。

后端启动后每 10 秒执行一次轻量级 Worker 检查。该检查不会主动调用 Gemini API，也不会为 Codex 或 Claude 创建任务。

### Codex 心跳

- 空闲时检查 `CODEX_APP_SERVER_COMMAND` 中的可执行文件是否存在；存在时显示 `ONLINE`，不存在时显示 `OFFLINE`。
- Codex AgentRun 启动后立即切换为 `RUNNING`。
- App Server 启动、WebSocket 连接和整个 Codex Turn 期间，每 10 秒刷新一次 `last_heartbeat_at`。
- Turn 成功后恢复 `ONLINE`；超时、未完成、WebSocket 异常或清理失败时变为 `FAILED`；进程无法启动时变为 `OFFLINE`。
- 多个 Codex run 并发时，最后一个活动 run 结束后才退出 `RUNNING`。
- 后端启动后发现数据库残留的 `RUNNING` 且心跳超过 30 秒时，将其恢复为 `FAILED`。
- Codex 继续使用现有稳定的 App Server 启动、WebSocket 通信和端口清理方式，心跳改造没有替换其进程执行链路。

### Claude 心跳

- 空闲时检查 `AGENT_CLAUDE_COMMAND` 中的可执行文件是否存在；存在时显示 `ONLINE`，不存在时显示 `OFFLINE`。
- Review 或 Recheck 启动后切换为 `RUNNING`。
- Claude CLI 子进程运行期间，每 10 秒刷新一次 `last_heartbeat_at`。
- 执行成功后恢复 `ONLINE`；失败或超时后变为 `FAILED`；CLI 无法启动时变为 `OFFLINE`。

### Gemini 心跳

- 只检查是否配置 `GEMINI_API_KEY`，不会通过额外探测请求消耗 API 配额。
- API Key 已配置且当前空闲时显示 `ONLINE`；未配置时显示 `OFFLINE`。
- `/gemini/test`、任务 brief、首页聊天和任务聊天调用期间显示 `RUNNING`。
- SSE 流式聊天在流真正结束前持续刷新心跳并保持 `RUNNING`。
- 调用成功后恢复 `ONLINE`；API 错误、网络错误或超时后变为 `FAILED`。
- 并发 Gemini 请求使用进程内活动计数，最后一个请求结束后才退出 `RUNNING`。
- `/gemini/tasks/{task_id}/facts` 和 diagnostic stream 不调用 Gemini API，因此不改变 Worker 状态。

## 工作流

前端显示 9 个阶段：

1. Requirement
2. Plan
3. Build
4. Review
5. Fix
6. Recheck
7. Accept
8. Archive
9. Done

后端状态机包含：

```text
REQUIREMENT_DRAFT
PLAN_REQUESTED
PLAN_READY
PLAN_CONFIRMED
IMPLEMENTING
IMPLEMENT_DONE
REVIEW_REQUESTED
REVIEW_DONE
FIX_REQUIRED
FIXING
FIX_DONE
RECHECK_REQUESTED
RECHECK_DONE
FINALIZE_REQUESTED
ACCEPTANCE_READY
ACCEPTANCE_PASSED
ARCHIVED
DONE
```

核心门禁约束：

- 不自动确认计划。
- 不自动通过验收。
- 不自动安装依赖。
- 不运行未注册的 shell 命令。
- 不让 Gemini 绕过 Human Supervisor。
- 不让 AgentHarness 直接越过 worker 修改外部业务项目代码。
- 不让 Codex 修改业务项目的 `REVIEW.md`，该文件由 Claude-DeepSeek 维护。

## 当前前端能力

任务详情页当前包含：

- 9 阶段 Flow State。
- 可编辑的 Requirement 面板。
- Agent Prompt 面板：实时预览提示词、选择模板、点击 Edit 后可手动编辑。
- Agent Runs 面板：展示执行历史、输出、诊断信息和运行证据。
- Workers 面板：展示数据库中的 `ONLINE`、`RUNNING`、`FAILED`、`OFFLINE` 状态和最近心跳，并通过 Pinia 与浮动 Agent 图标联动。
- Review Results 面板：读取并解析外部业务项目的 `REVIEW.md`。
- Safe Commands 面板：运行已注册安全命令。
- Events 面板：展示流程事件，面板内部滚动，避免把 Agent Runs 挤下去。

Flow State 可以触发这些 worker run：

- Plan：`codex_plan`
- Build：`codex_implement`
- Review：`claude_review`
- Fix：`codex_fix`
- Recheck：`claude_recheck`
- Accept 内部封板：`claude_finalize`
- Accept：`codex_acceptance_checklist`
- Archive：`codex_archive`

Agent Prompt 的手动编辑内容只有在“所选 prompt 类型”和“将要运行的 agent run 类型”匹配时，才会作为 `prompt_override` 发送给后端。不匹配时不会使用 override。

Accept 阶段的当前规则：

- 从 Review 或 Recheck 点击“进入验收”后，任务先进入内部状态 `FINALIZE_REQUESTED`，但前端仍显示第 07 个 Accept 大阶段。
- `FINALIZE_REQUESTED` 初始只显示“审查封板”；点击后运行 `claude_finalize`。
- `claude_finalize` 成功后显示“标记封板完成”；点击后进入 `ACCEPTANCE_READY`。
- 标记封板完成并进入 `ACCEPTANCE_READY` 后，蓝色“Codex 给出验收方案”作为正常下一步放在最左侧；“标记验收通过”保持白色禁用状态并放在右侧。
- `codex_acceptance_checklist` 成功后，“标记验收通过”启用、变为蓝色并移动到最左侧。
- 成功生成验收方案后，“Codex 给出验收方案”保留为重新生成入口，切换为白色循环按钮并移动到右侧。
- Flow State 的业务排序原则是：当前正常流程的下一步始终位于最左侧，重试、重新生成或尚未解锁的动作位于右侧。
- 后端也会校验：没有成功的 `codex_acceptance_checklist` 时，不能进入 `ACCEPTANCE_PASSED`。

Agent Runs 刷新规则：

- Flow State 任意按钮触发后，会立即刷新 Agent Runs。
- 最新 AgentRun 为 `RUNNING` 时，每 5 秒轮询一次。
- 运行完成后停止轮询。
- 最长轮询 10 分钟。

新建任务时，Workspace Path 支持前端记忆：

- 用户上一次成功创建任务使用的路径会保存在浏览器 localStorage。
- 下一次创建任务时，输入框可以视觉上保持为空。
- 如果用户不选择新路径，会默认使用上一次路径。
- placeholder 也显示上一次路径。

## 后端服务

当前主要 API：

- `/tasks`：创建、列表、详情、状态流转、更新需求。
- `/tasks/{task_id}/agent-runs`：查看和启动 AgentRun。
- `/tasks/{task_id}/prompts/preview`：预览将发送给 agent 的提示词。
- `/gemini/test`：验证 Gemini 原生 API 非流式文本调用。
- `/gemini/chat/stream`：首页 Gemini 对话流式回复。
- `/gemini/chat/diagnostic-stream`：不调用 Gemini 的 SSE 诊断流，用于排查前端/代理是否支持逐段刷新。
- `/gemini/tasks/{task_id}/facts`：为 Gemini Secretary 构建只读任务事实包。
- `/gemini/tasks/{task_id}/brief`：调用 Gemini Secretary 生成结构化任务简报。
- `/gemini/tasks/{task_id}/chat/stream`：任务详情页 Gemini 对话流式回复，基于当前任务 facts 生成上下文。
- `/reviews`：读取并解析 workspace 中的 `REVIEW.md`。
- `/commands`：运行已注册安全命令。
- `/filesystem`：选择 workspace 路径。
- `/workers`：查看 worker 状态。
- `/archive`：检查 README 归档覆盖情况。

首次安装且 `agentworker` 表完全为空时，后端会 seed 三个 worker：

- Codex
- Claude
- Gemini

后续启动不会覆盖数据库中的 Worker 名称、角色或 provider 类型。Agent provider 通过稳定的 `worker_key` 查找对应记录。

## Prompt 规则

提示词模板位于：

```text
backend/app/prompts/templates.py
```

当前 PromptType：

- `CODEX_PLAN`
- `CODEX_IMPLEMENT`
- `CLAUDE_REVIEW`
- `CODEX_FIX`
- `CLAUDE_RECHECK`
- `ACCEPTANCE_CHECKLIST`
- `README_ARCHIVE`

Prompt preview 是无状态的：根据当前任务和 prompt 类型实时生成。真正发送给 agent 的最终提示词会保存在 AgentRun 的 `input_payload` 中，方便后续追溯和复盘。

## Review 和 Archive

`REVIEW.md` 属于被评审的外部业务项目。Codex 可以读取和解析它，但不负责维护它。Claude-DeepSeek 负责评审和复审记录。

`README.md` 归档由 Codex 负责，因为 Codex 是实际开发者。Archive 阶段的目标是让 `README.md` 反映项目当前事实状态，而不是追加任务流水账。如果某次任务没有改变 应记录的当前事实，Codex 可以不修改`README.md`。

## 后端启动

创建并激活环境：

```bash
conda create -n agentharness python=3.11 -y
conda activate agentharness
```

安装依赖：

```bash
cd backend
pip install -e ".[dev]"
```

创建 `.env`，配置 MySQL 和本地 agent 命令：

```env
DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/agentharness
AGENT_TIMEOUT_SECONDS=600
CODEX_APP_SERVER_COMMAND=D:\NodeJS\codex.cmd app-server
AGENT_CLAUDE_COMMAND=C:\Users\<you>\.local\bin\claude.exe
GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com
GEMINI_PROXY_URL=http://127.0.0.1:7890
APP_TIMEZONE=Asia/Shanghai
```

启动后端：

```bash
cd backend
uvicorn app.main:app --reload
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

运行后端测试：

```bash
cd backend
pytest
```

## 前端启动

安装依赖并启动：

```bash
cd frontend
npm install
npm run dev
```

默认地址：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api` 代理到：

```text
http://127.0.0.1:8000
```

构建检查：

```bash
cd frontend
npm run build
```

## 当前限制

- Gemini 已接入前端 Secretary UI、任务 brief、首页/任务详情页对话框和原生 API 流式回复，但尚未具备自动调度权限。
- Gemini 对话目前是前端内存会话；关闭或刷新 Gemini 弹窗会清空当前对话，且聊天记录尚未持久化到数据库。
- Gemini 流式回复已经按 SSE delta 实时刷新前端，但首包时间仍取决于 Gemini 服务、代理节点和模型响应速度。
- 当前尚未持久化 Gemini API 调用日志，因此不能直接统计每个任务的调用次数、触发来源、耗时、首 Token 时间、token 用量、重试次数或成本。
- Codex / Claude 仍依赖本机 Codex App Server 和 Claude CLI；Gemini 通过受控后端服务调用，不能绕过后端 policy 或 Human Supervisor gate。
- Claude CLI 通过工具白名单禁用 Bash，但以当前 Windows 用户身份运行，并非操作系统级只读沙箱；当前主要依靠工具限制和提示词约束其写入范围。
- Human Supervisor 门禁保持人工决策。
- Safe Commands 只允许白名单命令。
