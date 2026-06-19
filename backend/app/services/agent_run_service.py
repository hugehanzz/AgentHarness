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
from app.models.worker import AgentRun, AgentSession, AgentSessionStatus, AgentWorker, RunStatus
from app.prompts.templates import build_prompt
from app.services.archive_check import check_readme_archive
from app.services.task_service import get_task_or_404


CODEX_APP_SERVER_RUN_TYPES = {
    "codex_plan": PromptType.CODEX_PLAN,
    "codex_implement": PromptType.CODEX_IMPLEMENT,
    "codex_fix": PromptType.CODEX_FIX,
    "codex_acceptance_checklist": PromptType.ACCEPTANCE_CHECKLIST,
    "codex_archive": PromptType.README_ARCHIVE,
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


CLAUDE_PROVIDER_TYPE = "claude_cli"
CLAUDE_SESSION_TASK_LIMIT = 5


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


def get_latest_claude_task_session(session: Session, task_id: int) -> AgentSession | None:
    latest_run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.task_id == task_id,
            AgentRun.provider_type == CLAUDE_PROVIDER_TYPE,
            AgentRun.agent_session_id.is_not(None),
        )
        .order_by(AgentRun.created_at.desc())
    ).first()
    if not latest_run or not latest_run.agent_session_id:
        return None
    return session.get(AgentSession, latest_run.agent_session_id)


def get_or_create_claude_session(session: Session, task_id: int, workspace_path: str) -> AgentSession:
    task_session = get_latest_claude_task_session(session, task_id)
    if task_session:
        return task_session

    active_session = session.exec(
        select(AgentSession)
        .where(
            AgentSession.provider_type == CLAUDE_PROVIDER_TYPE,
            AgentSession.workspace_path == workspace_path,
            AgentSession.status == AgentSessionStatus.ACTIVE,
        )
        .order_by(AgentSession.created_at.desc())
    ).first()
    if active_session and active_session.task_count < CLAUDE_SESSION_TASK_LIMIT:
        return active_session

    if active_session:
        active_session.status = AgentSessionStatus.ROTATED
        active_session.rotated_at = app_now()
        active_session.updated_at = app_now()
        session.add(active_session)

    new_session = AgentSession(
        provider_type=CLAUDE_PROVIDER_TYPE,
        workspace_path=workspace_path,
        status=AgentSessionStatus.ACTIVE,
    )
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    return new_session


def should_count_task_for_session(session: Session, agent_session_id: int, task_id: int) -> bool:
    existing_run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.agent_session_id == agent_session_id,
            AgentRun.task_id == task_id,
            AgentRun.provider_type == CLAUDE_PROVIDER_TYPE,
            AgentRun.status == RunStatus.SUCCEEDED,
        )
        .order_by(AgentRun.created_at.desc())
    ).first()
    return existing_run is None


def list_agent_runs(session: Session, task_id: int) -> list[AgentRun]:
    get_task_or_404(session, task_id)
    return list(
        session.exec(
            select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.created_at.desc())
        ).all()
    )


def resolve_prompt(task: Any, prompt_type: PromptType, prompt_override: str | None) -> str:
    if prompt_override and prompt_override.strip():
        return prompt_override.strip()
    return build_prompt(task, prompt_type)


async def run_agent(session: Session, task_id: int, run_type: str, prompt_override: str | None = None) -> AgentRun:
    if run_type in CODEX_APP_SERVER_RUN_TYPES:
        return await run_codex_app_server_agent(session, task_id, run_type, prompt_override)
    return await run_local_agent(session, task_id, run_type, prompt_override)


async def run_codex_app_server_agent(
    session: Session,
    task_id: int,
    run_type: str,
    prompt_override: str | None = None,
) -> AgentRun:
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
    prompt = resolve_prompt(task, CODEX_APP_SERVER_RUN_TYPES[run_type], prompt_override)
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
        if run_type == "codex_archive" and record.status == RunStatus.SUCCEEDED:
            apply_archive_check(record, str(cwd))
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


def apply_archive_check(record: AgentRun, workspace_path: str) -> None:
    try:
        result = check_readme_archive(workspace_path)
    except HTTPException as exc:
        record.status = RunStatus.FAILED
        record.error_message = f"Archive check failed: {exc.detail}"
        record.stderr = append_diagnostic_payload(record.stderr, {"archive_check_error": exc.detail})
        return

    record.stderr = append_diagnostic_payload(record.stderr, {"archive_check": result})
    missing = [
        key
        for key in ("has_acceptance_status", "has_test_results", "has_archive_notes", "has_next_steps")
        if result.get(key) is not True
    ]
    if missing:
        record.status = RunStatus.FAILED
        record.error_message = f"Archive check missing: {', '.join(missing)}"


def append_diagnostic_payload(existing: str | None, payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if existing and existing.strip():
        return f"{existing.rstrip()}\n\n{rendered}"
    return rendered


async def run_local_agent(
    session: Session,
    task_id: int,
    run_type: str,
    prompt_override: str | None = None,
) -> AgentRun:
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
    prompt = resolve_prompt(task, prompt_type, prompt_override)
    claude_session = get_or_create_claude_session(session, task.id, str(cwd))
    resume_session_id = claude_session.external_session_id
    task_should_be_counted = should_count_task_for_session(session, claude_session.id, task.id)
    run_command = build_claude_cli_command(command, resume_session_id)
    now = app_now()
    record = AgentRun(
        task_id=task.id,
        worker_id=worker.id if worker else None,
        agent_session_id=claude_session.id,
        run_type=run_type,
        provider_type=CLAUDE_PROVIDER_TYPE,
        command_display=display_claude_command(command, bool(resume_session_id)),
        cwd=str(cwd),
        status=RunStatus.RUNNING,
        input_payload=prompt,
        external_thread_id=resume_session_id,
        started_at=now,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            run_command,
            cwd=str(cwd),
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=settings.agent_timeout_seconds,
            check=False,
        )
        parsed = parse_claude_json_output(completed.stdout)
        session_id = extract_claude_session_id(parsed)
        record.exit_code = completed.returncode
        record.output_payload = extract_claude_result_text(parsed) or completed.stdout
        record.stderr = build_claude_diagnostics(completed.stderr, parsed)
        record.external_thread_id = session_id or resume_session_id
        record.external_turn_id = extract_claude_turn_id(parsed)
        record.status = RunStatus.SUCCEEDED if completed.returncode == 0 and not is_claude_error(parsed) else RunStatus.FAILED
        if completed.returncode != 0:
            record.error_message = completed.stderr or completed.stdout or f"Claude CLI exited with {completed.returncode}"
        if not parsed and completed.stdout:
            record.error_message = "Claude CLI did not return valid JSON"
            record.status = RunStatus.FAILED
        if record.status == RunStatus.SUCCEEDED and session_id:
            claude_session.external_session_id = session_id
            claude_session.status = AgentSessionStatus.ACTIVE
            claude_session.updated_at = app_now()
            if task_should_be_counted:
                claude_session.task_count += 1
            session.add(claude_session)
        elif record.status == RunStatus.FAILED and not claude_session.external_session_id:
            claude_session.status = AgentSessionStatus.FAILED
            claude_session.updated_at = app_now()
            session.add(claude_session)
    except subprocess.TimeoutExpired:
        record.status = RunStatus.TIMED_OUT
        record.error_message = "Claude CLI command timed out"
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


def build_claude_cli_command(command: list[str], resume_session_id: str | None) -> list[str]:
    cli_command = [
        *command,
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        "Read,Edit,MultiEdit,Glob,Grep",
        "--disallowedTools",
        "Bash",
    ]
    if resume_session_id:
        cli_command.extend(["--resume", resume_session_id])
    return cli_command


def display_claude_command(command: list[str], uses_resume: bool) -> str:
    suffix = " -p --output-format json --resume <session_id>" if uses_resume else " -p --output-format json"
    return f"{' '.join(command)}{suffix}"


def parse_claude_json_output(stdout: str) -> dict[str, Any] | None:
    if not stdout.strip():
        return None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_claude_session_id(parsed: dict[str, Any] | None) -> str | None:
    if not parsed:
        return None
    for key in ("session_id", "sessionId", "sessionID"):
        value = parsed.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def extract_claude_turn_id(parsed: dict[str, Any] | None) -> str | None:
    if not parsed:
        return None
    value = parsed.get("uuid")
    return value if isinstance(value, str) and value else None


def extract_claude_result_text(parsed: dict[str, Any] | None) -> str | None:
    if not parsed:
        return None
    value = parsed.get("result")
    return value if isinstance(value, str) else None


def is_claude_error(parsed: dict[str, Any] | None) -> bool:
    if not parsed:
        return False
    return bool(parsed.get("is_error")) or parsed.get("subtype") == "error"


def build_claude_diagnostics(stderr: str, parsed: dict[str, Any] | None) -> str | None:
    diagnostics: dict[str, Any] = {}
    if stderr:
        diagnostics["stderr"] = stderr
    if parsed:
        diagnostics["result_type"] = parsed.get("type")
        diagnostics["subtype"] = parsed.get("subtype")
        diagnostics["is_error"] = parsed.get("is_error")
        diagnostics["session_id"] = parsed.get("session_id")
        diagnostics["uuid"] = parsed.get("uuid")
        diagnostics["duration_ms"] = parsed.get("duration_ms")
        diagnostics["num_turns"] = parsed.get("num_turns")
        diagnostics["total_cost_usd"] = parsed.get("total_cost_usd")
        diagnostics["permission_denials"] = parsed.get("permission_denials")
        diagnostics["terminal_reason"] = parsed.get("terminal_reason")
        diagnostics["modelUsage"] = parsed.get("modelUsage")
    return json.dumps(diagnostics, ensure_ascii=False, indent=2) if diagnostics else None


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
        read_only_run_types = {"codex_plan", "codex_acceptance_checklist"}
        sandbox = "read-only" if run_type in read_only_run_types else "workspace-write"
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
