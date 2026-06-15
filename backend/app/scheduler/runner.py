import asyncio
from contextlib import suppress

from app.scheduler.queue import QueueJob, task_queue


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            job = await asyncio.wait_for(task_queue.get(), timeout=1)
        except TimeoutError:
            continue
        try:
            await execute_job(job)
        except Exception as exc:
            job.errors.append(str(exc))
            if job.retries < job.max_retries:
                job.retries += 1
                await task_queue.enqueue(job)
        finally:
            task_queue.task_done()


async def execute_job(job: QueueJob) -> None:
    # The first version keeps queue execution observable but minimal. API paths
    # execute user-triggered jobs directly so results are returned immediately.
    await asyncio.sleep(0)


async def stop_task(task: asyncio.Task | None) -> None:
    if not task:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
