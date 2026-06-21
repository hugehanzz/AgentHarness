# AgentHarness

AgentHarness 是一个本地运行、由 Human Supervisor 监督的多 Agent 研发工作流控制台。项目目标是把“需求 -> 计划 -> 开发 -> [ 评审 -> 修复 -> 复审 ] -> 验收 -> 归档”的研发链路产品化，让 Codex、Claude 等本地 Agent 在可观测、可追溯、可人工介入的流程中协作。

当前版本不直接调用 OpenAI、Claude 或 DeepSeek 云端 API，而是通过本机 Codex App Server 和 Claude CLI 接入受控 worker；Gemini 作为系统内部秘书能力，通过受控后端服务调用 Gemini 原生 API。AgentHarness 负责流程编排、状态机、提示词构建、证据保存、人类门禁和前端操作台；真正的代码生成和评审动作发生在用户选择的业务项目 workspace 中。

## 当前架构

- 后端：Python 3.11、FastAPI、SQLModel、MySQL、asyncio。
- 前端：Vue 3、Vite、Element Plus、Pinia。
- 测试数据库：后端测试使用 SQLite，不依赖 MySQL。
- 运行数据库：MySQL。
- 本地 Agent 接入：Codex App Server、Claude CLI。
- 系统内部 AI：Gemini Secretary，通过后端调用 Gemini 原生 API。

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
- Workers 面板：展示当前 worker 状态。
- Review Results 面板：读取并解析外部业务项目的 `REVIEW.md`。
- Safe Commands 面板：运行已注册安全命令。
- Events 面板：展示流程事件，面板内部滚动，避免把 Agent Runs 挤下去。

Flow State 可以触发这些 worker run：

- Plan：`codex_plan`
- Build：`codex_implement`
- Review：`claude_review`
- Fix：`codex_fix`
- Recheck：`claude_recheck`
- Accept：`codex_acceptance_checklist`
- Archive：`codex_archive`

Agent Prompt 的手动编辑内容只有在“所选 prompt 类型”和“将要运行的 agent run 类型”匹配时，才会作为 `prompt_override` 发送给后端。不匹配时不会使用 override。

Accept 阶段的当前规则：

- 从 Recheck 进入 Accept 后，先只显示“运行 Codex 验收建议”。
- `codex_acceptance_checklist` 成功后，才显示“标记验收通过”。
- 成功生成验收建议后，“运行 Codex 验收建议”保留为重新生成入口，图标切换为循环样式。
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

## Gemini Agent Roadmap

Gemini 会分阶段从系统秘书升级为流程协调员，核心原则是：Gemini 读取后端提供的事实，可以总结和提出动作建议，但不能直接修改状态机，也不能绕过 Human Supervisor gate。

### Current Status

- 后端已接入 Gemini 原生 API，而不是 OpenAI-compatible 路径：
  - 非流式文本调用使用 `models/{model}:generateContent`。
  - 对话流式调用使用 `models/{model}:streamGenerateContent?alt=sse`。
- Gemini API key 从 `GEMINI_API_KEY` 读取；本地代理可通过 `GEMINI_PROXY_URL` 配置，例如 `http://127.0.0.1:7890`。
- 任务详情页已具备 Gemini Secretary 对话框：
  - 点击 Gemini 悬浮图标打开对话框。
  - 打开任务详情页时，Gemini brief 会基于 `facts_version` 缓存；关键阶段会后台预热，避免点击后空白等待。
  - 用户输入后，后端通过 SSE 返回 Gemini 回复，前端按 delta 实时刷新消息气泡。
  - 任务状态变化时，任务详情页会清理该任务下的人类聊天消息，避免旧上下文污染新阶段。
- 首页点击 Gemini 悬浮图标也会打开同款对话框，默认展示固定问候“你好，我是Gemini~”；首页刷新或关闭 Gemini 对话框时，会清空首页人类消息。
- 前端当前有三个可拖动悬浮 agent 图标：Codex、Claude、Gemini。它们保持独立拖动，并带有防重叠推开约束。
- Gemini 当前仍是 Secretary Mode：可以总结、解释、问答和建议，但不触发 worker run、不修改任务状态、不批准计划、不批准验收。

### Stage 1: Secretary Mode

- 后端从任务状态、事件、AgentRun、ReviewItem、CommandRun、gate 和允许流转中构建只读事实包。
- Gemini 基于事实包总结当前进度、解释当前 gate、提示风险并建议下一步。
- Gemini 不修改任务状态、不触发 worker run、不批准计划、不批准验收。

### Stage 2: Action Proposal Mode

- Gemini 可以输出结构化动作建议，例如 `REQUEST_REVIEW`、`REQUEST_RECHECK`、`START_ARCHIVE`。
- 动作建议只是 proposal，不是执行权限。
- 计划确认和最终验收始终属于 Human Supervisor。

### Stage 3: Policy-Checked Execution

- 后端根据状态机、当前事实、允许流转和 human gate 规则校验 Gemini proposal。
- Gemini 永远不直接写状态机。
- 被拒绝的 proposal 应该能向用户解释原因。

### Stage 4: Auto Scheduling

- 低风险且通过 policy 校验的动作可以自动执行，例如实现完成后请求 review、修复完成后请求 recheck、验收通过后触发 archive。
- 高风险动作、依赖安装、外部业务项目修改决策、计划确认和验收通过仍由 Human Supervisor 控制。

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

后端启动时只会创建或更新三个 worker：

- Codex
- Claude
- Gemini

如果旧数据库里还有早期实验留下的 worker 行，需要人工按需清理。

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
- Gemini 对话目前是前端会话级缓存；尚未持久化聊天记录到数据库。
- Gemini 流式回复已经按 SSE delta 实时刷新前端，但首包时间仍取决于 Gemini 服务、代理节点和模型响应速度。
- Codex / Claude 仍依赖本机 Codex App Server 和 Claude CLI；Gemini 通过受控后端服务调用，不能绕过后端 policy 或 Human Supervisor gate。
- Human Supervisor 门禁保持人工决策。
- Safe Commands 只允许白名单命令。
- 旧数据库可能仍有历史 worker 行或空遗留表，需要人工清理。
