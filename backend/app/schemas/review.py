from pydantic import BaseModel


class ReviewParseRequest(BaseModel):
    workspace_path: str
    task_id: int | None = None


class ParsedReviewItem(BaseModel):
    severity: str
    title: str
    description: str | None = None
    status: str = "OPEN"


class ReviewParseResult(BaseModel):
    review_path: str
    current_task: str | None
    high_count: int
    medium_count: int
    low_count: int
    open_count: int
    recheck_status: str
    items: list[ParsedReviewItem]
