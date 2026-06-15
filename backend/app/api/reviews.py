from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.review import ReviewParseRequest, ReviewParseResult
from app.services.review_parser import parse_review_file

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("/parse", response_model=ReviewParseResult)
def parse(payload: ReviewParseRequest, session: Session = Depends(get_session)):
    return parse_review_file(payload.workspace_path, session=session, task_id=payload.task_id)
