from typing import Awaitable, Callable, Optional

from golem_core.managers.activity.defaults import (
    default_on_activity_start,
    default_on_activity_stop,
)
from golem_core.managers.base import ActivityManager, Work, WorkResult


class SingleUseActivityManager(ActivityManager):
    def __init__(
        self,
        get_agreement: Callable[[], Awaitable["Agreement"]],
        on_activity_start: Optional[Work] = default_on_activity_start,
        on_activity_stop: Optional[Work] = default_on_activity_stop,
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

    async def do_work(self, work) -> WorkResult:
        activity = await self.get_activity()

        if self._on_activity_start:
            await activity.do(self._on_activity_start)

        try:
            result = await activity.do(work)
        except Exception as e:
            result = WorkResult(exception=e)

        if self._on_activity_stop:
            await activity.do(self._on_activity_stop)

        return result
