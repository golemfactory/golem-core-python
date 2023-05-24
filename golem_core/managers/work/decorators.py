import asyncio
from functools import wraps

from golem_core.managers.base import DoWorkCallable, Work, WorkDecorator, WorkResult


def work_decorator(decorator: WorkDecorator):
    def _work_decorator(work: Work):
        if not hasattr(work, "_work_decorators"):
            work._work_decorators = []

        work._work_decorators.append(decorator)

        return work

    return _work_decorator


def retry(tries: int = 3):
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

            work_result.extras["retry"] = {
                "tries": count,
                "errors": errors,
            }

            return work_result

        return wrapper

    return _retry


def redundancy_cancel_others_on_first_done(size: int = 3):
    def _redundancy(do_work: DoWorkCallable):
        @wraps(do_work)
        async def wrapper(work: Work) -> WorkResult:
            tasks = [do_work(work) for _ in range(size)]

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
