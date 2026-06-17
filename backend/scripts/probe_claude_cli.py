from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_WORKSPACE = Path(r"D:\codexProject\AgentHarnessTest")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "tmp" / "claude_cli_probe_result.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Claude CLI JSON output, session_id capture, and --resume behavior."
    )
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Workspace where Claude should run.")
    parser.add_argument("--claude", default="claude", help="Claude CLI executable.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON file for probe evidence.")
    parser.add_argument(
        "--permission-mode",
        default="acceptEdits",
        choices=["acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan"],
        help="Claude permission mode for the probe.",
    )
    return parser.parse_args()


def run_claude(
    *,
    claude: str,
    workspace: Path,
    prompt: str,
    permission_mode: str,
    resume_session_id: str | None = None,
) -> dict[str, Any]:
    command = [
        claude,
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        permission_mode,
        "--allowedTools",
        "Read,Edit,MultiEdit,Glob,Grep",
        "--disallowedTools",
        "Bash",
    ]
    if resume_session_id:
        command.extend(["--resume", resume_session_id])

    completed = subprocess.run(
        command,
        cwd=workspace,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    parsed: dict[str, Any] | None = None
    parse_error = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    return {
        "command": redact_command(command),
        "cwd": str(workspace),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "json": parsed,
        "json_parse_error": parse_error,
    }


def redact_command(command: list[str]) -> list[str]:
    return ["<prompt-via-stdin>" if item == "-" else item for item in command]


def extract_session_id(result: dict[str, Any]) -> str | None:
    parsed = result.get("json")
    if not isinstance(parsed, dict):
        return None
    for key in ("session_id", "sessionId", "sessionID"):
        value = parsed.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_review_prompt() -> str:
    return """你是当前 Java 测试工程的 ReviewerAgent。

这是 AgentHarness 的 Claude CLI session/resume 接入验证，不是正式业务审查。

请执行以下动作：
1. 读取当前目录的 CLAUDE.md、AGENTS.md 和 REVIEW.md。
2. 不要修改 Java 代码，不要运行命令，不要调用 Bash。
3. 只更新 REVIEW.md，在“当前审查任务”或合适位置写入一条测试审查记录。
4. 在机器可读状态 JSON 中把 current_task 设置为“Claude CLI resume probe”，review_status 设置为 “REVIEWED”，needs_codex_action 设置为 false。
5. 回复请使用简体中文，并明确说明“probe review complete”。
"""


def build_recheck_prompt() -> str:
    return """请继续上一轮 Claude CLI resume probe。

请执行以下动作：
1. 确认你能看到上一轮关于 “Claude CLI resume probe” 的上下文。
2. 读取 REVIEW.md。
3. 只更新 REVIEW.md 的复审信息或摘要，把 recheck_status 设置为 “PASSED”。
4. 不要修改 Java 代码，不要运行命令，不要调用 Bash。
5. 回复请使用简体中文，并明确说明“probe recheck complete”。
"""


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if not workspace.exists() or not workspace.is_dir():
        print(f"Workspace does not exist: {workspace}", file=sys.stderr)
        return 2

    review = run_claude(
        claude=args.claude,
        workspace=workspace,
        prompt=build_review_prompt(),
        permission_mode=args.permission_mode,
    )
    session_id = extract_session_id(review)

    recheck = None
    if review["returncode"] == 0 and session_id:
        recheck = run_claude(
            claude=args.claude,
            workspace=workspace,
            prompt=build_recheck_prompt(),
            permission_mode=args.permission_mode,
            resume_session_id=session_id,
        )

    evidence = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "workspace": str(workspace),
        "permission_mode": args.permission_mode,
        "session_id": session_id,
        "review": review,
        "recheck": recheck,
        "succeeded": bool(
            review["returncode"] == 0
            and session_id
            and recheck
            and recheck["returncode"] == 0
            and "probe recheck complete" in recheck["stdout"]
        ),
    }
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"workspace: {workspace}")
    print(f"session_id: {session_id or '<missing>'}")
    print(f"review_returncode: {review['returncode']}")
    print(f"recheck_returncode: {recheck['returncode'] if recheck else '<skipped>'}")
    print(f"evidence: {output}")
    print(f"succeeded: {evidence['succeeded']}")
    return 0 if evidence["succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
