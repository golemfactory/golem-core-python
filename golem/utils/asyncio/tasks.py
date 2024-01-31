import asyncio
import contextvars
import inspect
import logging
from typing import Iterable, Optional, TypeVar, cast

from golem.utils.logging import trace_id_var
from golem.utils.typing import MaybeAwaitable

T = TypeVar("T")

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


async def ensure_cancelled(task: asyncio.Task) -> None:
    """Cancel given task and await for its cancellation."""

    if task.done():
        return

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass


async def ensure_cancelled_many(tasks: Iterable[asyncio.Task]) -> None:
    """Cancel given tasks and concurrently await for their cancellation."""

    await asyncio.gather(*[ensure_cancelled(task) for task in tasks])


async def resolve_maybe_awaitable(value: MaybeAwaitable[T]) -> T:
    """Return given value or await for it results if value is awaitable."""

    if inspect.isawaitable(value):
        return await value

    # TODO: remove cast as inspect.isawaitable can't tell mypy that at this
    #  point value is T
    return cast(T, value)
