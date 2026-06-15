import re
from pathlib import Path

from fastapi import HTTPException
from sqlmodel import Session

from app.models.review import ReviewItem, ReviewSeverity
from app.schemas.review import ParsedReviewItem, ReviewParseResult


SEVERITY_PATTERNS = {
    "HIGH": re.compile(r"\b(high|高|高危|严重)\b|^高[:：]", re.IGNORECASE),
    "MEDIUM": re.compile(r"\b(medium|中|中等)\b|^中[:：]", re.IGNORECASE),
    "LOW": re.compile(r"\b(low|低|轻微)\b|^低[:：]", re.IGNORECASE),
}


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
    recheck_status = _extract_recheck_status(content)

    if session and task_id is not None:
        for item in items:
            session.add(
                ReviewItem(
                    task_id=task_id,
                    severity=ReviewSeverity(item.severity),
                    title=item.title[:300],
                    description=item.description,
                    status=item.status,
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
    for index, line in enumerate(lines):
        normalized = line.strip().lower()
        if "current review task" in normalized or "当前审查任务" in normalized:
            for next_line in lines[index + 1 : index + 6]:
                value = next_line.strip(" #-")
                if value:
                    return value
    return None


def _extract_items(lines: list[str]) -> list[ParsedReviewItem]:
    items: list[ParsedReviewItem] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        status = "OPEN" if "[ ]" in stripped or any(key in stripped for key in ["待修复", "未解决", "TODO"]) else "RESOLVED"
        severity = _detect_severity(stripped)
        if severity == "UNKNOWN" and status != "OPEN":
            continue
        title = re.sub(r"^[-*]\s*(\[[ xX]\])?\s*", "", stripped)
        title = re.sub(r"^(High|Medium|Low|高|中|低|高危|中等|轻微)[:：]\s*", "", title, flags=re.IGNORECASE)
        items.append(ParsedReviewItem(severity=severity, title=title or stripped, status=status))
    return items


def _detect_severity(text: str) -> str:
    cleaned = text.strip("-* []")
    for severity, pattern in SEVERITY_PATTERNS.items():
        if pattern.search(cleaned):
            return severity
    return "UNKNOWN"


def _extract_recheck_status(content: str) -> str:
    if re.search(r"复审通过|recheck passed|passed", content, re.IGNORECASE):
        return "PASSED"
    if re.search(r"复审未通过|仍需修复|未通过|recheck failed|failed", content, re.IGNORECASE):
        return "FAILED"
    return "UNKNOWN"
