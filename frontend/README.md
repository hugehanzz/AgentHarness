# AgentHarness Frontend

## Setup

```bash
cd frontend
npm install
npm run dev
```

The development server proxies `/api` to `http://127.0.0.1:8000`.

## Build

```bash
npm run build
```

## Worker status

The Workers panel polls `/api/workers` every five seconds and renders the
database-backed `ONLINE`, `RUNNING`, `FAILED`, or `OFFLINE` state. A running
Claude worker also activates the Claude floating icon glow.
