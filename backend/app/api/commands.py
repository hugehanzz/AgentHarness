from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.command import CommandRunRead, CommandRunRequest
from app.services.command_service import run_safe_command

router = APIRouter(prefix="/commands", tags=["commands"])


@router.post("/run", response_model=CommandRunRead)
async def run(payload: CommandRunRequest, session: Session = Depends(get_session)):
    return await run_safe_command(session, payload.command_key, payload.workspace_path, payload.task_id)
