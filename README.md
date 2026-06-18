# AgentHarness

AgentHarness 是一个本地运行的、人类监督的 Agent 工作流控制台。它用于帮助 Human Supervisor 管理从需求录入、计划确认、开发实现、代码评审、问题修复、复查、验收到归档的完整流程。

当前版本不会直接调用 OpenAI、Claude、DeepSeek 或 Gemini API。系统通过本机已安装的 Codex / Claude CLI 能力接入受控 worker：Codex 通过 App Server 协议执行计划、开发、修复和 README 归档维护；Claude-DeepSeek 通过 Claude CLI 执行评审和复审，并维护业务项目中的 `REVIEW.md`；Gemini 暂定为第三个 agent，用于使用提醒、进度摘要、门禁提示和安全流程推进建议。AgentHarness 负责保存流程状态、提示词来源、Agent Run 证据、评审结果、验收清单、安全命令入口、worker 状态和事件记录。

## 当前范围

- 创建工作流任务：包含标题、工作区路径和需求描述。
- 在 Workflow Board 中展示任务数量、活跃流程、人工关卡、9 个阶段状态和更新时间。
- 打开任务详情页后，可以查看和操作：
  - 9 阶段 Flow State。
  - 可编辑的 Requirement 文本，作为提示词生成的重要来源。
  - Workers 状态概览。
  - Agent Runs，展示 Codex / Claude 执行结果、运行详情和诊断信息。
  - Prompt Builder 模板选择器，并根据当前 Flow State 默认推荐下一步模板。
  - Review Results，用于解析外部业务项目的 `REVIEW.md`。
  - Safe Commands 面板。
  - Human acceptance checklist。
  - Events 时间线，使用中文流程描述和可读时间格式。
- Flow State 可以直接调度受控 worker：
  - `Plan` 阶段运行 Codex Plan。
  - `Build` 阶段运行 Codex Implement。
  - `Review` 阶段运行 Claude Review。
  - `Fix` 阶段运行 Codex Fix。
  - `Recheck` 阶段运行 Claude Recheck。
- Flow State 每次进入新阶段后会自动刷新 Agent Runs，Agent 执行完成后也会再次刷新证据。
- Codex App Server 会在任务指定的 `workspace_path` 下启动，并复用同一任务的 Codex thread。
- Claude CLI 会在任务指定的 `workspace_path` 下启动，并复用 Claude `session_id`；同一 workspace 大约每 5 个不同任务轮换一次 Claude review session。
- 通过机器可读 JSON 块解析外部业务项目的 `REVIEW.md`。
- 保留 Human Supervisor 的人工关卡，不自动确认计划，也不自动通过验收。
- 已建立测试业务工程 `D:\codexProject\AgentHarnessTest`，用于开发阶段验证 Codex / Claude 协作链路。

## 当前仍未完成或暂时禁用的能力

当前前端暂时保留但禁用了以下按钮：

- `Build Prompt`
- `git status`
- `git diff --stat`

后端里可能仍然保留了提示词和安全命令相关接口，但当前前端不会主动触发这些能力。

Archive 阶段目前仍是 Human Supervisor 手动推进。业务设计上，归档内容应由 Codex 负责维护，因为 Codex 是实际开发者，README 是给 Codex 和人类开发者共同阅读的工程记忆。Archive checker 是 Codex 侧的归档辅助检查服务，用于检查业务项目根目录、前端、后端、App 端、数据库等位置的 `README.md` 是否覆盖验收状态、验证结果、归档说明和后续建议；`REVIEW.md` 仍只由 Claude-DeepSeek 维护。是否真正进入 `Done` 仍由 Human Supervisor 决定。

首页 `Human Gates` 当前统计两个核心人工关卡：

- `PLAN_READY`：计划待 Human Supervisor 确认。
- `ACCEPTANCE_READY`：最终验收待 Human Supervisor 确认。

后续可以扩展统计 `REVIEW_DONE`、`RECHECK_DONE`、`ACCEPTANCE_PASSED`、`ARCHIVED` 等需要人决策的状态。

## REVIEW.md 解析约定

AgentHarness 自己的仓库根目录不再维护 `REVIEW.md`。

对于被评审的业务项目，AgentHarness 会读取对应工作区下的文件：

```text
<workspace>/REVIEW.md
```

推荐在业务项目的 `REVIEW.md` 中加入 `## 机器可读状态` 章节，并在该章节下放置一个合法的 JSON 代码块：

```json
{
  "schema_version": 1,
  "current_task": "当前评审任务名称",
  "review_status": "ARCHIVED",
  "recheck_status": "PASSED",
  "needs_codex_action": false,
  "summary": "当前评审状态摘要",
  "issue_counts": {
    "HIGH": 0,
    "MEDIUM": 0,
    "LOW": 0
  },
  "issues": [
    {
      "id": "LOW-1",
      "severity": "LOW",
      "status": "WONT_FIX",
      "title": "问题标题",
      "description": "可选的问题描述"
    }
  ]
}
```

允许的枚举值：

- `review_status`: `NOT_STARTED`, `IN_REVIEW`, `REVIEWED`, `FIX_REQUIRED`, `RECHECKING`, `ARCHIVED`
- `recheck_status`: `NOT_REQUIRED`, `PENDING`, `PASSED`, `FAILED`
- `severity`: `HIGH`, `MEDIUM`, `LOW`
- `status`: `OPEN`, `FIXED_PENDING_RECHECK`, `CLOSED`, `WONT_FIX`

如果 `## 机器可读状态` 章节存在，但 JSON 无效，AgentHarness 会返回校验错误，不会继续从普通 Markdown 描述里猜测结果。  
如果没有机器可读 JSON 块，则会回退到旧版 Markdown 章节解析逻辑。

## 仓库文件

```text
AgentHarness/
+-- backend/
+-- frontend/
+-- README.md
+-- .gitignore
```

`AGENTS.md` 是本地协作说明文件，已加入 `.gitignore`。  
根目录 `REVIEW.md` 已删除；评审记录应该放在被评审的外部业务项目中。

## 后端启动

创建并激活 Conda 环境：

```bash
conda create -n agentharness python=3.11 -y
conda activate agentharness
```

安装后端依赖：

```bash
cd backend
pip install -e ".[dev]"
```

创建 `.env`：

```bash
copy .env.example .env
```

数据库配置示例：

```env
DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/agentharness
AGENT_TIMEOUT_SECONDS=600
CODEX_APP_SERVER_COMMAND=D:\NodeJS\codex.cmd app-server
AGENT_CLAUDE_COMMAND=C:\Users\<you>\.local\bin\claude.exe
APP_TIMEZONE=Asia/Shanghai
```

`CODEX_APP_SERVER_COMMAND` 应指向本机可执行的 Codex App Server 命令。  
`AGENT_CLAUDE_COMMAND` 应指向本机 Claude CLI 可执行文件。  
AgentHarness 会在任务的 `workspace_path` 下启动这些 worker，确保 Codex / Claude 面向正确工程工作。

启动后端：

```bash
uvicorn app.main:app --reload
```

API 文档地址：

```text
http://127.0.0.1:8000/docs
```

运行后端测试：

```bash
cd backend
conda run -n agentharness pytest
```

## 前端启动

安装依赖并启动开发服务器：

```bash
cd frontend
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

Vite 开发服务器会把 `/api` 代理到：

```text
http://127.0.0.1:8000
```

前端构建检查：

```bash
cd frontend
npm run build
```

## 角色说明

AgentWorker 只登记真正会作为独立执行主体运行的 agent，当前收敛为三个：

- CodexAgent：代表本地 Codex worker，通过 Codex App Server 执行计划、开发、修复和 README 归档维护。归档是 Codex 的开发者记忆职责，不交给评审 agent。
- ReviewerAgent：代表本地 Claude-DeepSeek worker，通过 Claude CLI 执行代码评审和复审，并维护业务项目的 `REVIEW.md`。
- GeminiAgent：第三个待接入 agent，定位为 AgentHarness 的“秘书”。它提醒使用者怎样使用系统、汇总开发进度、提示待处理门禁、建议可安全自动推进的流程动作，但不能代替 Human Supervisor 批准计划、依赖、验收或高风险修复。

以下能力不是 AgentWorker，而是控制面服务、工具或人工门禁：

- Human Supervisor：负责人类确认，包括需求、计划、依赖、高风险修复、最终验收和下一个模块决策。
- State machine / Prompt Builder：整理上下文、生成提示词、推进状态并推荐下一步。
- Acceptance checklist：生成验收清单并记录证据。
- Safe command executor：只运行已注册的安全命令。
- Review parser：只读解析 `REVIEW.md`，不修改它。
- Archive checker：Codex 侧辅助检查 README 归档完整性，可覆盖根目录、前端、后端、App 端、数据库等多份 README；不修改 `REVIEW.md`。

## Agent 接入状态

### Codex App Server

Codex 通过 App Server 方式接入：

```text
codex app-server --listen ws://127.0.0.1:<port>
```

后端负责：

- 为每次运行启动本地 App Server。
- 创建或恢复 Codex thread。
- 在任务 `workspace_path` 下启动 turn。
- Plan 阶段使用只读模式。
- Implement / Fix / Archive 阶段使用 workspace-write 模式。
- 保存 thread id、turn id、输出、诊断事件和执行状态。

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
- Review / Recheck 复用同一任务的 Claude session。
- 同一 workspace 下每 5 个不同任务自动轮换一次 Claude review session。
- 将 Claude 的中文结论展示在 Agent Runs 中，并把模型使用、权限拒绝、退出原因等信息放进 Diagnostics。

## 第一版不做的事

- 不直接调用 OpenAI、Claude、DeepSeek 或 Gemini API。
- 不绕过本地 Codex / Claude CLI 直接调用模型 API。
- 不让 AgentHarness 自己越过 worker 直接修改外部业务项目代码。
- 不让 Codex 修改业务项目 `REVIEW.md`；该文件由 Claude-DeepSeek 维护。
- 不让 GeminiAgent 越过 Human Supervisor 自动批准计划、依赖、验收或高风险修复。
- 不自动确认计划。
- 不自动通过验收。
- 未经 Human Supervisor 确认，不安装依赖。
- 不运行未注册的 shell 命令。

## 后续计划

- 完善 Archive 阶段：由 Codex 更新 README 归档，由 Codex 侧 archive checker 检查多份 README 归档材料完整性。
- 接入 GeminiAgent，用于使用提醒、进度摘要、门禁提示和安全流程推进建议。
- 重新启用 Prompt Builder，并把生成结果与 Flow State 调度打通。
- 重新启用 Safe Commands，并增加更清晰的输出展示和命令证据记录。
- 支持项目级提示词模板覆盖。
- 增加 `REVIEW.md` 机器 JSON 和普通 Markdown 描述之间的一致性检查。
- 在首页更准确地区分 Human Gates、Active Flows 和 Agent Running。
- 增加更完整的队列、迁移和生产化部署能力。
