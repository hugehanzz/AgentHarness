# AgentHarness

AgentHarness is a local multi-agent R&D workflow orchestration system for Codex, Claude-DeepSeek, and a Human Supervisor.

It is not a generic task board. It manages the full local R&D flow from requirement drafting, planning, implementation, review, fixing, recheck, acceptance, archive, and next-step recommendation.

## Positioning

AgentHarness follows a Harness-style control plane and data plane split:

- Controller: task scheduling, state transitions, retries, and result aggregation.
- Task Queue: in-process asyncio queue for the first version.
- Worker Agents: prompt building, review parsing, safe commands, and archive checks.
- Heartbeat Monitor: reports worker online, offline, idle, and running state.
- Result Aggregator: stores prompts, command results, review items, acceptance items, and task events.

## Tech Stack

- Backend: Python 3.11, FastAPI, SQLModel, MySQL, asyncio.
- Backend environment: Conda environment named `agentharness`.
- Frontend: Vue 3, Vite, Element Plus, Pinia, TypeScript.
- Command execution: `asyncio.create_subprocess_exec` with registered command keys only.

## First Version Scope

- Human-in-the-loop DeveloperAgent and ReviewerAgent.
- Read-only REVIEW.md parsing.
- Whitelist-based safe command execution.
- Prompt templates for Codex, Claude-DeepSeek, acceptance, and README archive work.
- Human Supervisor gates for plan confirmation and final acceptance.
- No direct OpenAI, Claude, or DeepSeek API calls.

## Explicit Non-Goals

- No automatic business project code edits.
- No automatic REVIEW.md edits.
- No automatic plan approval.
- No automatic acceptance approval.
- No automatic dependency installation.
- No arbitrary shell command execution.
- No complex permission system or multi-user collaboration.

## Repository Layout

```text
AgentHarness/
+-- AGENTS.md
+-- REVIEW.md
+-- backend/
+-- frontend/
+-- README.md
```

## Run Backend

```bash
conda create -n agentharness python=3.11 -y
conda activate agentharness
cd backend
pip install -e ".[dev]"
copy .env.example .env
uvicorn app.main:app --reload
```

Update `.env` with your MySQL connection:

```env
DATABASE_URL=mysql+pymysql://agentharness:agentharness@localhost:3306/agentharness
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend proxies `/api` to `http://127.0.0.1:8000`.

## Agent Division

- OrchestratorAgent: generates prompts and recommends next states.
- DeveloperAgent: external Codex worker in the first version.
- ReviewerAgent: external Claude-DeepSeek worker in the first version.
- AcceptanceAgent: manages acceptance checklist and evidence.
- CommandWorker: runs registered safe commands.
- ReviewParserWorker: parses REVIEW.md.
- ArchiveCheckWorker: checks README archive completeness.

## Future Expansion

- LocalCodexWorker can wrap locally installed Codex tooling.
- LocalClaudeWorker can wrap locally installed Claude tooling.
- Queue implementation can move from in-memory `asyncio.Queue` to Redis or another durable broker.
- Database migrations can be added with Alembic when schema changes become frequent.
