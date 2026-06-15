# AGENTS.md

## Project

AgentHarness is a local multi-agent R&D workflow orchestration system based on Harness-style control plane and data plane separation.

## Roles

- Human Supervisor: owns requirements, plan approval, dependency approval, high-risk fix approval, final acceptance, and next-module decisions.
- OrchestratorAgent: organizes requirements, builds prompts, advances states, and recommends the next step.
- DeveloperAgent: represents Codex. In the first version it is an external human-in-the-loop worker.
- ReviewerAgent: represents Claude-DeepSeek. In the first version it maintains REVIEW.md externally.
- AcceptanceAgent: builds acceptance checklists and records evidence.
- CommandWorker: runs registered safe commands only.
- ReviewParserWorker: reads and parses REVIEW.md without modifying it.
- ArchiveCheckWorker: checks README archive completeness without modifying it.

## Non-Negotiable Gates

- Do not confirm plans automatically.
- Do not approve acceptance automatically.
- Do not install dependencies without Human Supervisor confirmation.
- Do not run unregistered shell commands.
- Do not modify external business project code automatically.
- Do not modify REVIEW.md automatically.
- Do not call OpenAI, Claude, or DeepSeek APIs in the first version.

## Development Rules

- Backend: Python 3.11, FastAPI, SQLModel, MySQL, asyncio.
- Backend environment: Conda environment named `agentharness`.
- Frontend: Vue 3, Vite, Element Plus, Pinia.
- Command execution must use a whitelist and `asyncio.create_subprocess_exec`.
- REVIEW.md parsing is read-only.
- SQLite may be used only for tests.

## Review Rules

- Claude-DeepSeek maintains REVIEW.md.
- Codex reads REVIEW.md and fixes issues after the Human Supervisor approves the direction when required.
- Review results should include severity, open items, and recheck conclusion.
