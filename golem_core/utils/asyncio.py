import asyncio
import logging

logger = logging.getLogger(__name__)

def create_task_with_logging(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    task.add_done_callback(_handle_task_logging)
    return task

def _handle_task_logging(task: asyncio.Task):
    try:
        return task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception('Background async task encountered unhandled exception!')
