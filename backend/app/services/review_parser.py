import re
from pathlib import Path

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

OPEN_MARKERS = ("[ ]", "待修复", "未解决", "TODO")
RESOLVED_MARKERS = ("[x]", "[X]", "已修复", "关闭", "通过")
WONT_FIX_MARKERS = ("暂不处理", "不处理", "可选优化")


def parse_review_file(workspace_path: str, session: Session | None = None, task_id: int | None = None) -> ReviewParseResult:
    root = Path(workspace_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")
    review_path = root / "REVIEW.md"
    if not review_path.exists():
        raise HTTPException(status_code=404, detail="REVIEW.md not found")

    content = review_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    current_task = _extract_current_task(lines)
    items = _extract_items(lines)
    recheck_status = _extract_recheck_status(lines)

    if session and task_id is not None:
        session.exec(delete(ReviewItem).where(ReviewItem.task_id == task_id))
        for item in items:
            session.add(
                ReviewItem(
                    task_id=task_id,
                    severity=ReviewSeverity(item.severity),
                    title=item.title[:300],
                    description=item.description,
                    status=ReviewItemStatus(item.status),
                    source_file=str(review_path),
                )
            )
        session.commit()

    return ReviewParseResult(
        review_path=str(review_path),
        current_task=current_task,
        high_count=sum(1 for item in items if item.severity == "HIGH"),
        medium_count=sum(1 for item in items if item.severity == "MEDIUM"),
        low_count=sum(1 for item in items if item.severity == "LOW"),
        open_count=sum(1 for item in items if item.status == "OPEN"),
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
        return "RESOLVED"
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
        return "UNKNOWN"
    if re.search(r"不通过|未通过|failed|failure", conclusion_text, re.IGNORECASE):
        return "FAILED"
    if re.search(r"通过|passed|pass", conclusion_text, re.IGNORECASE):
        return "PASSED"
    return "UNKNOWN"


def _section_after_heading(lines: list[str], headings: tuple[str, ...]) -> list[str]:
    section: list[str] = []
    collecting = False
    for line in lines:
        normalized = line.strip().strip("# ").lower()
        if line.lstrip().startswith("#"):
            if collecting:
                break
            if any(heading in normalized for heading in headings):
                collecting = True
            continue
        if collecting:
            section.append(line)
    return _without_history(section)


def _without_history(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        normalized = line.strip().strip("# ").lower()
        if line.lstrip().startswith("#") and any(heading in normalized for heading in HISTORY_HEADINGS):
            break
        result.append(line)
    return result
