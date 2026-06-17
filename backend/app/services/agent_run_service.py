import asyncio
import json
import os
import shlex
import socket
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select
import websockets

from app.core.config import get_settings
from app.models.common import app_now
from app.models.prompt import PromptType
from app.models.task import TaskEvent
from app.models.worker import AgentRun, AgentWorker, RunStatus
from app.prompts.templates import build_prompt
from app.services.task_service import get_task_or_404


CODEX_APP_SERVER_RUN_TYPES = {
    "codex_plan": PromptType.CODEX_PLAN,
    "codex_implement": PromptType.CODEX_IMPLEMENT,
    "codex_fix": PromptType.CODEX_FIX,
}


LOCAL_CLI_RUN_DEFINITIONS: dict[str, dict[str, str]] = {
    "claude_review": {
        "worker_name": "Claude-DeepSeek",
        "prompt_type": PromptType.CLAUDE_REVIEW,
        "command_setting": "agent_claude_command",
    },
    "claude_recheck": {
        "worker_name": "Claude-DeepSeek",
        "prompt_type": PromptType.CLAUDE_RECHECK,
        "command_setting": "agent_claude_command",
    },
}


def split_command(command_value: str) -> list[str]:
    if os.name == "nt":
        parts = shlex.split(command_value, posix=False)
        return [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'" else part
            for part in parts
        ]
    return shlex.split(command_value)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get_latest_codex_thread_id(session: Session, task_id: int) -> str | None:
    latest_run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.task_id == task_id,
            AgentRun.provider_type == "codex_app_server",
            AgentRun.external_thread_id.is_not(None),
        )
        .order_by(AgentRun.created_at.desc())
    ).first()
    return latest_run.external_thread_id if latest_run else None


def list_agent_runs(session: Session, task_id: int) -> list[AgentRun]:
    get_task_or_404(session, task_id)
    return list(
        session.exec(
            select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.created_at.desc())
        ).all()
    )


async def run_agent(session: Session, task_id: int, run_type: str) -> AgentRun:
    if run_type in CODEX_APP_SERVER_RUN_TYPES:
        return await run_codex_app_server_agent(session, task_id, run_type)
    return await run_local_agent(session, task_id, run_type)


async def run_codex_app_server_agent(session: Session, task_id: int, run_type: str) -> AgentRun:
    if run_type not in CODEX_APP_SERVER_RUN_TYPES:
        raise HTTPException(status_code=400, detail="Codex run type is not registered")

    task = get_task_or_404(session, task_id)
    if not task.workspace_path:
        raise HTTPException(status_code=400, detail="Task workspace_path is required")

    cwd = Path(task.workspace_path).expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")

    settings = get_settings()
    command = split_command(settings.codex_app_server_command)
    if not command:
        raise HTTPException(status_code=400, detail="CODEX_APP_SERVER_COMMAND is empty")

    worker = session.exec(select(AgentWorker).where(AgentWorker.name == "Codex")).first()
    prompt = build_prompt(task, CODEX_APP_SERVER_RUN_TYPES[run_type])
    existing_thread_id = get_latest_codex_thread_id(session, task.id)
    now = app_now()
    record = AgentRun(
        task_id=task.id,
        worker_id=worker.id if worker else None,
        run_type=run_type,
        provider_type="codex_app_server",
        command_display=f"{' '.join(command)} --listen ws://127.0.0.1:<port>",
        cwd=str(cwd),
        status=RunStatus.RUNNING,
        input_payload=prompt,
        external_thread_id=existing_thread_id,
        started_at=now,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    app_server: CodexAppServerProcess | None = None
    try:
        app_server = await CodexAppServerProcess.start(command, str(cwd))
        result = await asyncio.wait_for(
            app_server.run_turn(prompt, str(cwd), existing_thread_id, run_type),
            timeout=settings.agent_timeout_seconds,
        )
        record.external_thread_id = result["thread_id"]
        record.external_turn_id = result["turn_id"]
        record.output_payload = result["agent_text"]
        record.stderr = result["diagnostics"]
        record.status = RunStatus.SUCCEEDED if result["completed"] else RunStatus.FAILED
        if not result["completed"]:
            record.error_message = "Codex turn did not complete"
    except TimeoutError:
        record.status = RunStatus.TIMED_OUT
        record.error_message = f"Codex App Server run timed out after {settings.agent_timeout_seconds} seconds"
    except (OSError, RuntimeError, websockets.WebSocketException) as exc:
        record.status = RunStatus.FAILED
        record.error_message = str(exc) or repr(exc)
    finally:
        if app_server:
            await app_server.stop()
        record.finished_at = app_now()
        session.add(record)
        session.add(
            TaskEvent(
                task_id=task.id,
                event_type="AGENT_RUN_COMPLETED",
                message=f"{run_type}: {record.status}",
                created_by="agentharness",
            )
        )
        session.commit()
        session.refresh(record)

    return record


async def run_local_agent(session: Session, task_id: int, run_type: str) -> AgentRun:
    if run_type not in LOCAL_CLI_RUN_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Agent run type is not registered")

    task = get_task_or_404(session, task_id)
    if not task.workspace_path:
        raise HTTPException(status_code=400, detail="Task workspace_path is required")

    cwd = Path(task.workspace_path).expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")

    definition = LOCAL_CLI_RUN_DEFINITIONS[run_type]
    settings = get_settings()
    command_value = getattr(settings, definition["command_setting"])
    if not command_value:
        raise HTTPException(
            status_code=400,
            detail=f"{definition['command_setting'].upper()} is not configured",
        )

    command = split_command(command_value)
    if not command:
        raise HTTPException(status_code=400, detail="Configured agent command is empty")

    worker = session.exec(select(AgentWorker).where(AgentWorker.name == definition["worker_name"])).first()
    prompt_type = PromptType(definition["prompt_type"])
    prompt = build_prompt(task, prompt_type)
    now = app_now()
    record = AgentRun(
        task_id=task.id,
        worker_id=worker.id if worker else None,
        run_type=run_type,
        provider_type="local_cli",
        command_display=" ".join(command),
        cwd=str(cwd),
        status=RunStatus.RUNNING,
        input_payload=prompt,
        started_at=now,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(prompt.encode("utf-8")),
            timeout=settings.agent_timeout_seconds,
        )
        record.exit_code = proc.returncode
        record.output_payload = stdout_bytes.decode("utf-8", errors="replace")
        record.stderr = stderr_bytes.decode("utf-8", errors="replace")
        record.status = RunStatus.SUCCEEDED if proc.returncode == 0 else RunStatus.FAILED
    except TimeoutError:
        record.status = RunStatus.TIMED_OUT
        record.error_message = "Agent command timed out"
    except OSError as exc:
        record.status = RunStatus.FAILED
        record.error_message = str(exc)
    finally:
        record.finished_at = app_now()
        session.add(record)
        session.add(
            TaskEvent(
                task_id=task.id,
                event_type="AGENT_RUN_COMPLETED",
                message=f"{run_type}: {record.status}",
                created_by="agentharness",
            )
        )
        session.commit()
        session.refresh(record)

    return record


class CodexAppServerProcess:
    def __init__(self, proc: subprocess.Popen, port: int):
        self.proc = proc
        self.port = port
        self.next_request_id = 1

    @classmethod
    async def start(cls, command: list[str], cwd: str) -> "CodexAppServerProcess":
        port = find_free_port()
        proc = subprocess.Popen(
            [*command, "--listen", f"ws://127.0.0.1:{port}"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(1)
        return cls(proc, port)

    async def stop(self) -> None:
        if os.name == "nt":
            await asyncio.to_thread(
                subprocess.run,
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f"Get-NetTCPConnection -LocalPort {self.port} -State Listen -ErrorAction SilentlyContinue | "
                        "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
                    ),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(self.proc.wait), timeout=3)
            except asyncio.TimeoutError:
                self.proc.kill()
                await asyncio.to_thread(self.proc.wait)

    async def run_turn(self, prompt: str, cwd: str, thread_id: str | None, run_type: str) -> dict[str, Any]:
        sandbox = "read-only" if run_type == "codex_plan" else "workspace-write"
        async with await self.connect() as ws:
            await self.request(
                ws,
                "initialize",
                {
                    "clientInfo": {"name": "agentharness", "title": "AgentHarness", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            await ws.send(json.dumps({"method": "initialized"}))
            if thread_id:
                thread_response = await self.request(
                    ws,
                    "thread/resume",
                    {
                        "threadId": thread_id,
                        "cwd": cwd,
                        "approvalPolicy": "never",
                        "sandbox": sandbox,
                        "persistExtendedHistory": True,
                    },
                )
            else:
                thread_response = await self.request(
                    ws,
                    "thread/start",
                    {
                        "cwd": cwd,
                        "approvalPolicy": "never",
                        "sandbox": sandbox,
                        "experimentalRawEvents": False,
                        "persistExtendedHistory": True,
                    },
                )
            active_thread_id = thread_response["thread"]["id"]
            turn_response = await self.request(
                ws,
                "turn/start",
                {
                    "threadId": active_thread_id,
                    "input": [{"type": "text", "text": prompt, "text_elements": []}],
                    "cwd": cwd,
                    "approvalPolicy": "never",
                },
            )
            turn_id = turn_response["turn"]["id"]
            return await self.collect_turn(ws, active_thread_id, turn_id)

    async def connect(self) -> Any:
        last_error: Exception | None = None
        for _ in range(20):
            try:
                return await websockets.connect(f"ws://127.0.0.1:{self.port}", open_timeout=5)
            except (OSError, websockets.WebSocketException) as exc:
                last_error = exc
                await asyncio.sleep(0.5)
        raise RuntimeError(f"Could not connect to Codex App Server: {last_error}")

    async def request(self, ws: Any, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_request_id
        self.next_request_id += 1
        await ws.send(json.dumps({"id": request_id, "method": method, "params": params}))
        while True:
            payload = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if payload.get("id") == request_id:
                if "error" in payload:
                    raise RuntimeError(json.dumps(payload["error"], ensure_ascii=False))
                return payload.get("result") or {}

    async def collect_turn(self, ws: Any, thread_id: str, turn_id: str) -> dict[str, Any]:
        agent_text: list[str] = []
        diagnostics: list[dict[str, Any]] = []
        completed = False
        while True:
            payload = json.loads(await ws.recv())
            method = payload.get("method")
            params = payload.get("params") or {}
            if method == "item/agentMessage/delta" and params.get("turnId") == turn_id:
                agent_text.append(params.get("delta", ""))
            elif method in {
                "error",
                "warning",
                "thread/tokenUsage/updated",
                "thread/status/changed",
                "mcpServer/startupStatus/updated",
                "turn/started",
            }:
                diagnostics.append(payload)
            elif method == "turn/completed" and params.get("turn", {}).get("id") == turn_id:
                completed = params.get("turn", {}).get("status") == "completed"
                turn_error = params.get("turn", {}).get("error")
                if turn_error:
                    diagnostics.append(payload)
                break
            elif "id" in payload and method:
                diagnostics.append(payload)
        return {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "agent_text": "".join(agent_text),
            "diagnostics": json.dumps(diagnostics, ensure_ascii=False, indent=2) if diagnostics else None,
            "completed": completed,
        }
