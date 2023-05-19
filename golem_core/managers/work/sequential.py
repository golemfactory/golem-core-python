from functools import partial
from typing import List

from golem_core.managers.base import DoWorkCallable, Work, WorkResult


class SequentialWorkManager:
    def __init__(self, do_work: DoWorkCallable):
        self._do_work = do_work

    def apply_work_decorators(self, do_work: DoWorkCallable, work: Work) -> DoWorkCallable:
        if not hasattr(work, "_work_decorators"):
            return do_work

        result = do_work
        for dec in work._work_decorators:
            result = partial(dec, result)

        return result

    async def do_work(self, work: Work) -> WorkResult:
        decorated_do_work = self.apply_work_decorators(self._do_work, work)

        return await decorated_do_work(work)

    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        results = []

        for work in work_list:
            results.append(await self.do_work(work))

        return results
