# AgentHarness Backend

FastAPI backend for the AgentHarness local multi-agent workflow controller.

## Conda Setup

```bash
conda create -n agentharness python=3.11 -y
conda activate agentharness
cd backend
pip install -e ".[dev]"
```

Or:

```bash
conda env create -f environment.yml
conda activate agentharness
```

## Configuration

Copy `.env.example` to `.env` and update `DATABASE_URL` plus local agent settings as needed.

```env
DATABASE_URL=mysql+pymysql://agentharness:agentharness@localhost:3306/agentharness
CODEX_APP_SERVER_COMMAND=codex app-server
AGENT_CLAUDE_COMMAND=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com
GEMINI_PROXY_URL=
```

Create the MySQL database before first run:

```sql
CREATE DATABASE agentharness CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'agentharness'@'localhost' IDENTIFIED BY 'agentharness';
GRANT ALL PRIVILEGES ON agentharness.* TO 'agentharness'@'localhost';
FLUSH PRIVILEGES;
```

## Run

```bash
uvicorn app.main:app --reload
```

## Worker registry

`agentworker` is the source of truth for worker identity and display metadata.
The backend locates integrations by immutable `worker_key` values (`codex`,
`claude`, and `gemini`) and does not overwrite existing names, roles, or
provider types during startup.

Claude is currently the first provider with a complete worker lifecycle:

- `OFFLINE`: the configured Claude executable is unavailable.
- `ONLINE`: the Claude CLI is available and idle.
- `RUNNING`: a review or recheck subprocess is active; heartbeat is refreshed.
- `FAILED`: the latest Claude run failed or timed out.

Gemini uses the same state vocabulary for API calls:

- API key missing: `OFFLINE`.
- API key configured and idle: `ONLINE`.
- Brief generation or chat streaming active: `RUNNING`, with a refreshed
  heartbeat until the request or stream ends.
- API error or timeout: `FAILED`.

Concurrent Gemini requests are counted in the backend process, so the worker
stays `RUNNING` until the last active request finishes.

Codex uses its existing per-run App Server adapter without changing the stable
process or WebSocket implementation:

- configured command unavailable: `OFFLINE`;
- command available and idle: `ONLINE`;
- App Server startup and the complete WebSocket turn: `RUNNING`, with heartbeat;
- startup failure: `OFFLINE`;
- timeout, incomplete turn, WebSocket failure, or cleanup failure: `FAILED`.

Concurrent Codex runs keep the worker in `RUNNING` until the final active run
finishes. A stale `RUNNING` record with no in-process run and a heartbeat older
than 30 seconds is recovered as `FAILED`.

## Review finalization

The nine visible workflow stages are unchanged. Entering acceptance from Review
or Recheck now moves the task into the internal `FINALIZE_REQUESTED` state,
which is displayed inside stage 07 Accept.

Claude responsibilities are split across three registered run types:

- `claude_review`: initial code review and issue creation;
- `claude_recheck`: verify fixes and update issue/recheck status, without sealing;
- `claude_finalize`: validate that no open issues remain and finalize/archive
  `REVIEW.md` without performing another general code review.

A successful `claude_finalize` run is required before the
`FINALIZE_REQUESTED -> ACCEPTANCE_READY` transition can be completed.

## Test

```bash
pytest
```

Tests use SQLite in memory and do not require MySQL.
