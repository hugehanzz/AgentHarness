# AgentHarness

AgentHarness 是一个基于 Harness 思想的本地多智能体研发流程调度系统，用于管理 Codex、Claude-DeepSeek 与 Human Supervisor 协作完成需求、方案、开发、审查、修复、复审、验收、归档这一整套研发流程。

它不是普通任务看板，而是面向本地研发协作流程的控制台。第一版不会直接调用 OpenAI、Claude 或 DeepSeek API，而是把 Codex 和 Claude-DeepSeek 作为外部 Human-in-the-loop Worker 接入。

## 项目定位

AgentHarness 参考 Harness 的控制面 / 数据面分离思想：

- Controller：负责任务调度、状态流转、异常重试和结果汇总。
- Task Queue：第一版使用进程内 `asyncio.Queue`。
- Worker Agent：负责任务执行、提示词生成、审查解析、命令执行和归档检查。
- Heartbeat Monitor：检测 Worker 在线、离线、空闲、执行中状态。
- Result Aggregator：汇总提示词、命令结果、审查结果、验收项和任务事件。

## 技术栈

- 后端：Python 3.11、FastAPI、SQLModel、MySQL、asyncio。
- 后端环境：Conda 环境 `agentharness`。
- 前端：Vue 3、Vite、Element Plus、Pinia、TypeScript。
- 命令执行：后端使用 `asyncio.create_subprocess_exec`，只允许执行已登记的安全命令。
- 时间处理：第一版按 `Asia/Shanghai` 北京时间写入数据库。

## 第一版范围

- 支持创建任务并按照研发流程推进状态。
- 支持生成 Codex / Claude-DeepSeek / 验收 / 归档提示词。
- 支持读取并解析工作区中的 `REVIEW.md`。
- 支持执行白名单安全命令，例如 `git status`、`git diff --stat`。
- 支持 Worker 心跳展示。
- 支持验收项记录。
- 保留 Human Supervisor Gate，不自动确认方案、不自动确认验收。

## 第一版不做

- 不直接调用 OpenAI / Claude / DeepSeek API。
- 不自动修改业务项目代码。
- 不自动修改 `REVIEW.md`。
- 不自动确认方案。
- 不自动确认验收通过。
- 不自动安装依赖。
- 不执行未登记的任意 Shell 命令。
- 不做复杂权限系统。
- 不做多用户协作。

## 目录结构

```text
AgentHarness/
+-- AGENTS.md
+-- REVIEW.md
+-- backend/
+-- frontend/
+-- README.md
```

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

根据本机 MySQL 修改 `.env`：

```env
DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/agentharness
APP_TIMEZONE=Asia/Shanghai
```

启动后端：

```bash
uvicorn app.main:app --reload
```

访问接口文档：

```text
http://127.0.0.1:8000/docs
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端默认访问：

```text
http://127.0.0.1:5173
```

前端开发服务器会将 `/api` 代理到：

```text
http://127.0.0.1:8000
```

## Agent 分工

- OrchestratorAgent：整理需求、生成提示词、推进状态、判断下一步。
- DeveloperAgent：对应 Codex。第一版作为外部 Worker，由系统生成提示词，用户复制给 Codex 执行。
- ReviewerAgent：对应 Claude-DeepSeek。第一版作为外部 Worker，负责审查代码并维护 `REVIEW.md`。
- AcceptanceAgent：生成验收清单、记录验收证据，最终仍由 Human Supervisor 确认。
- CommandWorker：执行预定义安全命令并保存输出、退出码和耗时。
- ReviewParserWorker：只读解析 `REVIEW.md`，提取审查任务、问题级别和复审结论。
- ArchiveCheckWorker：检查 README 是否记录验收状态、测试结果和下一步建议。

## Human Supervisor Gate

Human Supervisor 不是普通用户，而是流程中的关键 Gate Owner，负责：

- 提出原始需求。
- 确认 Codex 方案。
- 确认新增依赖。
- 确认数据库迁移。
- 确认高风险修复方向。
- 最终验收通过。
- 决定是否进入下一模块。

系统不能绕过这些 Gate 自动推进。

## 后续扩展

- 增加 LocalCodexWorker，用于调用本地已安装的 Codex 工具。
- 增加 LocalClaudeWorker，用于调用本地已安装的 Claude 工具。
- 将 `asyncio.Queue` 替换为 Redis 等持久化队列。
- 引入 Alembic 管理数据库迁移。
- 增强 REVIEW.md 解析规范和去重逻辑。
- 增强任务详情页，使其成为完整流程控制台。
