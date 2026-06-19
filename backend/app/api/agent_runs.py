from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.agent_run import AgentRunCreate, AgentRunRead
from app.services.agent_run_service import list_agent_runs, run_agent

router = APIRouter(prefix="/tasks/{task_id}/agent-runs", tags=["agent-runs"])


@router.get("", response_model=list[AgentRunRead])
def list_for_task(task_id: int, session: Session = Depends(get_session)):
    return list_agent_runs(session, task_id)


@router.post("", response_model=AgentRunRead)
async def run(task_id: int, payload: AgentRunCreate, session: Session = Depends(get_session)):
    return await run_agent(session, task_id, payload.run_type, payload.prompt_override)
