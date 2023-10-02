import asyncio
import contextvars
import logging

from golem.utils.logging import trace_id_var

logger = logging.getLogger(__name__)


def create_task_with_logging(coro, *, trace_id=None) -> asyncio.Task:
    context = contextvars.copy_context()
    return context.run(_create_task_with_logging, coro, trace_id=trace_id)


def _create_task_with_logging(coro, *, trace_id=None) -> asyncio.Task:
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
