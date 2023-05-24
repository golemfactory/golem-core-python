from typing import Awaitable, Callable, Optional

from golem_core.managers.activity.defaults import (
    default_on_activity_start,
    default_on_activity_stop,
)
from golem_core.managers.base import ActivityManager, Work, WorkResult, WorkContext


class SingleUseActivityManager(ActivityManager):
    def __init__(
        self,
        get_agreement: Callable[[], Awaitable["Agreement"]],
        on_activity_start: Optional[Callable[[WorkContext], Awaitable[None]]] = default_on_activity_start,
        on_activity_stop: Optional[Callable[[WorkContext], Awaitable[None]]] = default_on_activity_stop,
    ):
        self._get_agreement = get_agreement
        self._on_activity_start = on_activity_start
        self._on_activity_stop = on_activity_stop

    async def get_activity(self) -> "Activity":
        while True:
            # We need to release agreement if is not used
            agreement = await self._get_agreement()
            try:
                return await agreement.create_activity()
            except Exception:
                pass

    async def do_work(self, work: Work) -> WorkResult:
        activity = await self.get_activity()
        work_context = WorkContext(activity)

        if self._on_activity_start:
            await self._on_activity_start(work_context)

        try:
            work_result = await work(work_context)
        except Exception as e:
            work_result = WorkResult(exception=e)
        else:
            if not isinstance(work_result, WorkResult):
                work_result = WorkResult(result=work_result)

        if self._on_activity_stop:
            await self._on_activity_stop(work_context)

        return work_result