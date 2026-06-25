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
stays `RUNNING` until the last active request finishes. Codex remains `OFFLINE`
until its provider-specific status probe is implemented.

## Test

```bash
pytest
```

Tests use SQLite in memory and do not require MySQL.
