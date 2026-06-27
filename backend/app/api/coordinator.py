from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.coordinator import CoordinatorRunResult, CoordinatorStepResult
from app.services.coordinator_service import run_coordinator_step, run_coordinator_until_blocked

router = APIRouter(prefix="/coordinator", tags=["coordinator"])


@router.post("/tasks/{task_id}/step", response_model=CoordinatorStepResult)
async def step(task_id: int, session: Session = Depends(get_session)):
    return await run_coordinator_step(session, task_id)


@router.post("/tasks/{task_id}/run", response_model=CoordinatorRunResult)
async def run(
    task_id: int,
    max_steps: int = Query(default=10, ge=1, le=20),
    session: Session = Depends(get_session),
):
    return await run_coordinator_until_blocked(session, task_id, max_steps=max_steps)
