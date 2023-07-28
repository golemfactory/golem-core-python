import asyncio
import logging
from functools import wraps
from typing import List

from golem.managers.base import (
    WORK_PLUGIN_FIELD_NAME,
    DoWorkCallable,
    Work,
    WorkManagerPlugin,
    WorkResult,
)

logger = logging.getLogger(__name__)


def work_plugin(plugin: WorkManagerPlugin):
    def _work_plugin(work: Work):
        if not hasattr(work, WORK_PLUGIN_FIELD_NAME):
            setattr(work, WORK_PLUGIN_FIELD_NAME, [])

        getattr(work, WORK_PLUGIN_FIELD_NAME).append(plugin)

        return work

    return _work_plugin


def retry(tries: int):
    def _retry(do_work: DoWorkCallable) -> DoWorkCallable:
        @wraps(do_work)
        async def wrapper(work: Work) -> WorkResult:
            count = 0
            errors = []
            work_result = WorkResult()

            while count <= tries:
                work_result = await do_work(work)

                if work_result.exception is None:
                    break

                count += 1
                errors.append(work_result.exception)

                logger.info(
                    f"Got an exception {work_result.exception} on {count} attempt {tries-count}"
                    "attempts left"
                )

            work_result.extras["retry"] = {
                "tries": count,
                "errors": errors,
            }

            return work_result

        return wrapper

    return _retry


def redundancy_cancel_others_on_first_done(size: int):
    def _redundancy(do_work: DoWorkCallable):
        @wraps(do_work)
        async def wrapper(work: Work) -> WorkResult:
            tasks: List[asyncio.Task] = [asyncio.ensure_future(do_work(work)) for _ in range(size)]

            tasks_done, tasks_pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            for task in tasks_pending:
                task.cancel()

            for task in tasks_pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            return tasks_done.pop().result()

        return wrapper

    return _redundancy
