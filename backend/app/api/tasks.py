from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.task import TaskCreate, TaskDetail, TaskRead, TaskTransitionRequest
from app.services.task_service import create_task, get_task_events, get_task_or_404, list_tasks, transition_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead)
def create(payload: TaskCreate, session: Session = Depends(get_session)):
    return create_task(session, payload)


@router.get("", response_model=list[TaskRead])
def list_all(session: Session = Depends(get_session)):
    return list_tasks(session)


@router.get("/{task_id}", response_model=TaskDetail)
def detail(task_id: int, session: Session = Depends(get_session)):
    task = get_task_or_404(session, task_id)
    events = get_task_events(session, task_id)
    return TaskDetail(task=task, events=events)


@router.post("/{task_id}/transition", response_model=TaskRead)
def transition(task_id: int, payload: TaskTransitionRequest, session: Session = Depends(get_session)):
    return transition_task(session, task_id, payload.to_status, payload.message, payload.created_by)
