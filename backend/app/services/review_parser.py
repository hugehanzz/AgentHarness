import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, delete

from app.models.review import ReviewItem, ReviewItemStatus, ReviewSeverity
from app.schemas.review import ParsedReviewItem, ReviewParseResult


SEVERITY_PATTERNS = {
    "HIGH": re.compile(r"\bhigh\b|高|高危|严重", re.IGNORECASE),
    "MEDIUM": re.compile(r"\bmedium\b|中|中等", re.IGNORECASE),
    "LOW": re.compile(r"\blow\b|低|轻微", re.IGNORECASE),
}

CURRENT_TASK_HEADINGS = ("current review task", "当前审查任务")
CURRENT_ISSUE_HEADINGS = ("open issues", "当前待处理问题")
RECHECK_HEADINGS = ("recheck conclusion", "当前模块复审记录")
HISTORY_HEADINGS = ("历史审查归档", "history")
MACHINE_STATE_HEADING = "机器可读状态"

OPEN_MARKERS = ("[ ]", "待修复", "未解决", "TODO")
RESOLVED_MARKERS = ("[x]", "[X]", "已修复", "关闭", "通过")
WONT_FIX_MARKERS = ("暂不处理", "不处理", "可选优化")

REVIEW_STATUSES = {"NOT_STARTED", "IN_REVIEW", "REVIEWED", "FIX_REQUIRED", "RECHECKING", "ARCHIVED"}
RECHECK_STATUSES = {"NOT_REQUIRED", "PENDING", "PASSED", "FAILED"}
ISSUE_STATUSES = {"OPEN", "FIXED_PENDING_RECHECK", "CLOSED", "WONT_FIX"}
OPEN_ISSUE_STATUSES = {"OPEN", "FIXED_PENDING_RECHECK"}


def parse_review_file(workspace_path: str, session: Session | None = None, task_id: int | None = None) -> ReviewParseResult:
    root = Path(workspace_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")
    review_path = root / "REVIEW.md"
    if not review_path.exists():
        raise HTTPException(status_code=404, detail="REVIEW.md not found")

    content = review_path.read_text(encoding="utf-8")
    # 当 Claude 写入机器可读的 JSON 块时优先使用它；回退到 markdown 启发式方法以使旧的 REVIEW.md 文件保持可读。
    parsed = _parse_machine_state(content, str(review_path)) or _parse_markdown_state(content, str(review_path))
    _persist_items(parsed.items, session, task_id, str(review_path))
    return parsed


def _persist_items(
    items: list[ParsedReviewItem],
    session: Session | None,
    task_id: int | None,
    review_path: str,
) -> None:
    if not session or task_id is None:
        return

    # REVIEW.md 对 AgentHarness 是外部的且只读的；我们仅将解析的项目镜像到数据库中以供过滤、facts 和 UI 显示使用。
    session.exec(delete(ReviewItem).where(ReviewItem.task_id == task_id))
    for item in items:
        session.add(
            ReviewItem(
                task_id=task_id,
                severity=ReviewSeverity(item.severity),
                title=item.title[:300],
                description=item.description,
                status=ReviewItemStatus(item.status),
                source_file=review_path,
            )
        )
    session.commit()


def _parse_machine_state(content: str, review_path: str) -> ReviewParseResult | None:
    extracted = _extract_machine_json_block(content)
    if extracted is None:
        return None
    block, block_start_line = extracted

    try:
        state = json.loads(block)
    except json.JSONDecodeError as exc:
        repaired_block = _repair_machine_json_smart_quotes(block)
        if repaired_block != block:
            try:
                state = json.loads(repaired_block)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=422,
                    detail=_format_machine_json_error(exc, block, block_start_line),
                ) from exc
        else:
            raise HTTPException(
                status_code=422,
                detail=_format_machine_json_error(exc, block, block_start_line),
            ) from exc

    _validate_machine_state(state)
    items = [
        ParsedReviewItem(
            severity=issue["severity"],
            title=issue["title"],
            description=issue.get("description"),
            status=issue["status"],
        )
        for issue in state["issues"]
    ]
    counts = state["issue_counts"]
    return ReviewParseResult(
        review_path=review_path,
        current_task=state["current_task"] or None,
        high_count=counts["HIGH"],
        medium_count=counts["MEDIUM"],
        low_count=counts["LOW"],
        open_count=sum(1 for item in items if item.status in OPEN_ISSUE_STATUSES),
        recheck_status=state["recheck_status"],
        items=items,
    )


def _extract_machine_json_block(content: str) -> tuple[str, int] | None:
    lines = content.splitlines()
    section_start = _find_heading_index(lines, (MACHINE_STATE_HEADING,))
    if section_start is None:
        return None

    blocks: list[tuple[str, int]] = []
    collecting = False
    current: list[str] = []
    current_start_line = 0
    for index, line in enumerate(lines[section_start + 1 :], start=section_start + 2):
        if line.lstrip().startswith("#") and not collecting:
            break
        stripped = line.strip()
        if stripped == "```json":
            if collecting:
                raise HTTPException(status_code=422, detail="Nested REVIEW.md machine JSON block")
            collecting = True
            current = []
            current_start_line = index + 1
            continue
        if collecting and stripped == "```":
            collecting = False
            blocks.append(("\n".join(current), current_start_line))
            current = []
            current_start_line = 0
            continue
        if collecting:
            current.append(line)

    if collecting:
        raise HTTPException(status_code=422, detail="Unclosed REVIEW.md machine JSON block")
    if len(blocks) > 1:
        raise HTTPException(status_code=422, detail="REVIEW.md machine state must contain exactly one JSON block")
    return blocks[0] if blocks else None


def _find_heading_index(lines: list[str], headings: tuple[str, ...]) -> int | None:
    for index, line in enumerate(lines, start=1):
        normalized = line.strip().strip("# ").lower()
        if line.lstrip().startswith("#") and any(heading.lower() in normalized for heading in headings):
            return index - 1
    return None


def _format_machine_json_error(exc: json.JSONDecodeError, block: str, block_start_line: int) -> str:
    review_line = block_start_line + exc.lineno - 1
    block_lines = block.splitlines()
    bad_line = block_lines[exc.lineno - 1].strip() if 0 <= exc.lineno - 1 < len(block_lines) else ""
    hint = ""
    if exc.msg == "Expecting ',' delimiter" and '"' in bad_line:
        hint = "；常见原因是 JSON 字符串内出现未转义英文双引号，请改用中文引号或写成 \\\""
    if "“" in bad_line or "”" in bad_line:
        hint = "；JSON 字段名和字符串外壳必须使用英文半角双引号 \"，中文引号 “ ” 只能出现在字符串内容内部"
    return (
        f"Invalid REVIEW.md machine JSON at line {review_line}, column {exc.colno}: "
        f"{exc.msg}. Offending line: {bad_line}{hint}"
    )


def _repair_machine_json_smart_quotes(block: str) -> str:
    """Tolerate Claude using Chinese smart quotes as JSON syntax.

    This repair is intentionally narrow and in-memory only. It fixes obvious
    JSON syntax positions such as object keys and one-line string value
    delimiters, while preserving Chinese quotes inside string content.
    """
    lines = block.splitlines()
    repaired_lines: list[str] = []
    key_pattern = re.compile(r'(?P<prefix>^|[\s{,])[\u201c\u201d](?P<key>[A-Za-z_][A-Za-z0-9_]*)[\u201c\u201d](?P<suffix>\s*:)')
    value_pattern = re.compile(r'(?P<prefix>:\s*)[\u201c\u201d](?P<body>.*)[\u201c\u201d](?P<suffix>\s*,?\s*)$')

    for line in lines:
        repaired = key_pattern.sub(r'\g<prefix>"\g<key>"\g<suffix>', line)
        repaired = value_pattern.sub(r'\g<prefix>"\g<body>"\g<suffix>', repaired)
        repaired_lines.append(repaired)

    return "\n".join(repaired_lines)


def _validate_machine_state(state: Any) -> None:
    if not isinstance(state, dict):
        raise HTTPException(status_code=422, detail="REVIEW.md machine JSON must be an object")

    required = {
        "schema_version",
        "current_task",
        "review_status",
        "recheck_status",
        "needs_codex_action",
        "summary",
        "issue_counts",
        "issues",
    }
    missing = sorted(required - set(state))
    if missing:
        raise HTTPException(status_code=422, detail=f"REVIEW.md machine JSON missing fields: {', '.join(missing)}")

    if state["schema_version"] != 1:
        raise HTTPException(status_code=422, detail="Unsupported REVIEW.md machine JSON schema_version")
    if not isinstance(state["current_task"], str):
        raise HTTPException(status_code=422, detail="current_task must be a string")
    if state["review_status"] not in REVIEW_STATUSES:
        raise HTTPException(status_code=422, detail="review_status has an invalid value")
    if state["recheck_status"] not in RECHECK_STATUSES:
        raise HTTPException(status_code=422, detail="recheck_status has an invalid value")
    if not isinstance(state["needs_codex_action"], bool):
        raise HTTPException(status_code=422, detail="needs_codex_action must be a boolean")
    if not isinstance(state["summary"], str):
        raise HTTPException(status_code=422, detail="summary must be a string")

    counts = state["issue_counts"]
    if not isinstance(counts, dict):
        raise HTTPException(status_code=422, detail="issue_counts must be an object")
    for severity in ("HIGH", "MEDIUM", "LOW"):
        if not isinstance(counts.get(severity), int):
            raise HTTPException(status_code=422, detail=f"issue_counts.{severity} must be an integer")

    issues = state["issues"]
    if not isinstance(issues, list):
        raise HTTPException(status_code=422, detail="issues must be an array")
    for index, issue in enumerate(issues):
        _validate_machine_issue(issue, index)


def _validate_machine_issue(issue: Any, index: int) -> None:
    if not isinstance(issue, dict):
        raise HTTPException(status_code=422, detail=f"issues[{index}] must be an object")
    required = {"id", "severity", "status", "title"}
    missing = sorted(required - set(issue))
    if missing:
        raise HTTPException(status_code=422, detail=f"issues[{index}] missing fields: {', '.join(missing)}")
    if not isinstance(issue["id"], str):
        raise HTTPException(status_code=422, detail=f"issues[{index}].id must be a string")
    if issue["severity"] not in {"HIGH", "MEDIUM", "LOW"}:
        raise HTTPException(status_code=422, detail=f"issues[{index}].severity has an invalid value")
    if issue["status"] not in ISSUE_STATUSES:
        raise HTTPException(status_code=422, detail=f"issues[{index}].status has an invalid value")
    if not isinstance(issue["title"], str) or not issue["title"].strip():
        raise HTTPException(status_code=422, detail=f"issues[{index}].title must be a non-empty string")
    if "description" in issue and not isinstance(issue["description"], str):
        raise HTTPException(status_code=422, detail=f"issues[{index}].description must be a string")


def _parse_markdown_state(content: str, review_path: str) -> ReviewParseResult:
    lines = content.splitlines()
    current_task = _extract_current_task(lines)
    items = _extract_items(lines)
    recheck_status = _extract_recheck_status(lines)
    return ReviewParseResult(
        review_path=review_path,
        current_task=current_task,
        high_count=sum(1 for item in items if item.severity == "HIGH"),
        medium_count=sum(1 for item in items if item.severity == "MEDIUM"),
        low_count=sum(1 for item in items if item.severity == "LOW"),
        open_count=sum(1 for item in items if item.status in OPEN_ISSUE_STATUSES),
        recheck_status=recheck_status,
        items=items,
    )


def _extract_current_task(lines: list[str]) -> str | None:
    for line in _section_after_heading(lines, CURRENT_TASK_HEADINGS)[:6]:
        value = line.strip(" #-")
        if value:
            return value
    return None


def _extract_items(lines: list[str]) -> list[ParsedReviewItem]:
    items: list[ParsedReviewItem] = []
    for line in _section_after_heading(lines, CURRENT_ISSUE_HEADINGS):
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue

        severity = _detect_severity(stripped)
        if severity == "UNKNOWN":
            continue

        title = re.sub(r"^[-*]\s*(\[[ xX]\])?\s*", "", stripped)
        title = re.sub(
            r"^([（(]?\s*)?(High|Medium|Low|高|中|低|高危|中等|轻微)(\s*[）)]?)?[:：\s#-]*",
            "",
            title,
            flags=re.IGNORECASE,
        )
        items.append(ParsedReviewItem(severity=severity, title=title or stripped, status=_detect_status(stripped)))
    return items


def _detect_severity(text: str) -> str:
    cleaned = text.strip("-* []（）()")
    for severity, pattern in SEVERITY_PATTERNS.items():
        if pattern.search(cleaned):
            return severity
    return "UNKNOWN"


def _detect_status(text: str) -> str:
    if any(marker in text for marker in WONT_FIX_MARKERS):
        return "WONT_FIX"
    if any(marker in text for marker in OPEN_MARKERS):
        return "OPEN"
    if any(marker in text for marker in RESOLVED_MARKERS):
        return "CLOSED"
    return "OPEN"


def _extract_recheck_status(lines: list[str]) -> str:
    candidate_lines = [
        *_section_after_heading(lines, RECHECK_HEADINGS),
        *_section_after_heading(lines, CURRENT_TASK_HEADINGS),
    ]
    conclusion_text = "\n".join(
        line for line in candidate_lines if re.search(r"结论|conclusion|recheck", line, re.IGNORECASE)
    )
    if not conclusion_text:
        return "PENDING"
    if re.search(r"不通过|未通过|failed|failure", conclusion_text, re.IGNORECASE):
        return "FAILED"
    if re.search(r"通过|passed|pass", conclusion_text, re.IGNORECASE):
        return "PASSED"
    return "PENDING"


def _section_after_heading(lines: list[str], headings: tuple[str, ...]) -> list[str]:
    section: list[str] = []
    collecting = False
    for line in lines:
        normalized = line.strip().strip("# ").lower()
        if line.lstrip().startswith("#"):
            if collecting:
                break
            if any(heading.lower() in normalized for heading in headings):
                collecting = True
            continue
        if collecting:
            section.append(line)
    return _without_history(section)


def _without_history(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        normalized = line.strip().strip("# ").lower()
        if line.lstrip().startswith("#") and any(heading.lower() in normalized for heading in HISTORY_HEADINGS):
            break
        result.append(line)
    return result
