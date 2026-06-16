# AgentHarness

AgentHarness 是一个本地运行的、人类监督的 Agent 工作流控制台。它用于帮助 Human Supervisor 管理从需求录入、计划确认、开发实现、代码评审、问题修复、复查、验收到归档的完整流程。

第一版不会直接调用 OpenAI、Claude 或 DeepSeek API。Codex 和 Claude-DeepSeek 仍然作为外部人机协作 worker 存在；AgentHarness 负责保存流程状态、提示词来源、评审结果、验收清单、安全命令入口、worker 状态和事件记录。

## 当前范围

- 创建工作流任务：包含标题、工作区路径和需求描述。
- 在 Workflow Board 中展示任务数量、活跃流程、人工关卡、9 个阶段状态和更新时间。
- 打开任务详情页后，可以查看和操作：
  - 9 阶段 Flow State。
  - 可编辑的 Requirement 文本，作为提示词生成的重要来源。
  - Workers 状态概览。
  - Prompt Builder 模板选择器，并根据当前 Flow State 默认推荐下一步模板。
  - Review Results，用于解析外部业务项目的 `REVIEW.md`。
  - Safe Commands 面板。
  - Human acceptance checklist。
  - Events 时间线，使用中文流程描述和可读时间格式。
- 通过机器可读 JSON 块解析外部业务项目的 `REVIEW.md`。
- 保留 Human Supervisor 的人工关卡，不自动确认计划，也不自动通过验收。

## 暂时禁用的前端按钮

第一版前端暂时保留但禁用了以下按钮：

- `Build Prompt`
- `git status`
- `git diff --stat`

后端里可能仍然保留了提示词和安全命令相关接口，但当前前端不会主动触发这些能力。

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
APP_TIMEZONE=Asia/Shanghai
```

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

- Human Supervisor：负责人类确认，包括需求、计划、依赖、高风险修复、最终验收和下一个模块决策。
- OrchestratorAgent：整理需求、生成提示词、推进状态并推荐下一步。
- DeveloperAgent：第一版中代表外部 Codex worker。
- ReviewerAgent：第一版中代表外部 Claude-DeepSeek，并由它维护业务项目的 `REVIEW.md`。
- AcceptanceAgent：生成验收清单并记录证据。
- CommandWorker：只运行已注册的安全命令。
- ReviewParserWorker：只读解析 `REVIEW.md`，不修改它。
- ArchiveCheckWorker：检查 README 归档完整性，不修改业务项目。

## 第一版不做的事

- 不直接调用 OpenAI、Claude 或 DeepSeek API。
- 不自动修改外部业务项目代码。
- 不自动修改业务项目 `REVIEW.md`。
- 不自动确认计划。
- 不自动通过验收。
- 未经 Human Supervisor 确认，不安装依赖。
- 不运行未注册的 shell 命令。

## 后续计划

- 在模板内容和流程切换稳定后，重新启用 Prompt Builder。
- 重新启用 Safe Commands，并增加更清晰的输出展示和命令证据记录。
- 支持项目级提示词模板覆盖。
- 增加 `REVIEW.md` 机器 JSON 和普通 Markdown 描述之间的一致性检查。
- 增加业务项目 README 归档检查。
- 增加更完整的队列、迁移和生产化部署能力。
