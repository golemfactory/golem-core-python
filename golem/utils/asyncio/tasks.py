import asyncio
import contextvars
import logging
from typing import Optional, Sequence

from golem.utils.logging import trace_id_var

logger = logging.getLogger(__name__)


def create_task_with_logging(coro, *, trace_id: Optional[str] = None) -> asyncio.Task:
    context = contextvars.copy_context()
    task = context.run(_create_task_with_logging, coro, trace_id=trace_id)

    if trace_id is not None:
        task_name = trace_id
    else:
        task_name = task.get_name()

    logger.debug("Task `%s` created", task_name)

    return task


def _create_task_with_logging(coro, *, trace_id: Optional[str] = None) -> asyncio.Task:
    if trace_id is not None:
        trace_id_var.set(trace_id)

    task = asyncio.create_task(coro)
    task.add_done_callback(_handle_task_logging)
    return task


def _handle_task_logging(task: asyncio.Task):
    try:
        return task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Background async task encountered unhandled exception!")


async def cancel_and_await(task: asyncio.Task) -> None:
    if task.done():
        return

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass


async def cancel_and_await_many(tasks: Sequence[asyncio.Task]) -> None:
    await asyncio.gather(*[cancel_and_await(task) for task in tasks])