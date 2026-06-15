from fastapi import APIRouter
from pydantic import BaseModel

from app.services.archive_check import check_readme_archive

router = APIRouter(prefix="/archive", tags=["archive"])


class ArchiveCheckRequest(BaseModel):
    workspace_path: str


@router.post("/check")
def check(payload: ArchiveCheckRequest):
    return check_readme_archive(payload.workspace_path)
