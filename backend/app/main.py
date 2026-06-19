import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api import agent_runs, archive, commands, filesystem, prompts, reviews, tasks, workers
from app.core.config import get_settings
from app.core.database import engine, init_db
from app.scheduler.heartbeat import heartbeat_loop
from app.scheduler.runner import scheduler_loop, stop_task
from app.scheduler.workers import ensure_workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        ensure_workers(session)
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_loop(stop_event))
    scheduler_task = asyncio.create_task(scheduler_loop(stop_event))
    app.state.stop_event = stop_event
    yield
    stop_event.set()
    await stop_task(heartbeat_task)
    await stop_task(scheduler_task)


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(agent_runs.router)
app.include_router(prompts.router)
app.include_router(reviews.router)
app.include_router(commands.router)
app.include_router(filesystem.router)
app.include_router(workers.router)
app.include_router(archive.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
