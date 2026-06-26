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
Claude worker also activates the Claude floating icon glow. Worker polling is
owned by the top-level app and stored in Pinia, so both Claude and Gemini
floating icons receive status updates even when the Workers panel is not
mounted. Gemini keeps its immediate local request glow and also responds to the
backend `RUNNING` state. Codex uses the same backend state and shows a deeper
blue-purple version of the Gemini pulse and expanding ring.

## Accept finalization step

`FINALIZE_REQUESTED` is mapped to the existing Accept stage, so the workflow
still displays nine major stages. The UI first shows `审查封板`; after a
successful `claude_finalize` run it replaces that action with `标记封板完成`.
Completing the marker transition enters the existing acceptance-checklist flow.
