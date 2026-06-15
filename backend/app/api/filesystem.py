from fastapi import APIRouter, Query

from app.schemas.filesystem import FilesystemListResult, FilesystemRoots
from app.services.filesystem_service import list_directories, list_roots

router = APIRouter(prefix="/filesystem", tags=["filesystem"])


@router.get("/roots", response_model=FilesystemRoots)
def roots():
    return list_roots()


@router.get("/list", response_model=FilesystemListResult)
def list_path(path: str = Query(..., min_length=1)):
    return list_directories(path)
