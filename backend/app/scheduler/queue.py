import asyncio
from dataclasses import dataclass, field


@dataclass
class QueueJob:
    job_type: str
    payload: dict
    retries: int = 0
    max_retries: int = 2
    errors: list[str] = field(default_factory=list)


class TaskQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[QueueJob] = asyncio.Queue()

    async def enqueue(self, job: QueueJob) -> None:
        await self._queue.put(job)

    async def get(self) -> QueueJob:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def size(self) -> int:
        return self._queue.qsize()


task_queue = TaskQueue()
