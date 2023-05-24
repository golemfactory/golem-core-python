import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, Optional

from golem_core.core.activity_api import Activity
from golem_core.managers.activity.defaults import (
    default_on_activity_start,
    default_on_activity_stop,
)
from golem_core.managers.base import ActivityManager, Work, WorkContext, WorkResult

logger = logging.getLogger(__name__)


class SingleUseActivityManager(ActivityManager):
    def __init__(
        self,
        get_agreement: Callable[[], Awaitable["Agreement"]],
        event_bus,
        on_activity_start: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_start,
        on_activity_stop: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_stop,
    ):
        self._get_agreement = get_agreement
        self._event_bus = event_bus
        self._on_activity_start = on_activity_start
        self._on_activity_stop = on_activity_stop

    @asynccontextmanager
    async def _prepare_activity(self) -> Activity:
        while True:
            agreement = await self._get_agreement()

            try:
                yield await agreement.create_activity()
            except Exception:
                pass
            finally:
                self._event_bus.emit(AgreementReleased(agreement=agreement))

    async def do_work(self, work: Work) -> WorkResult:
        async with self._prepare_activity() as activity:
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

            if not activity.terminated:
                logger.warning(
                    "SingleUseActivityManager expects that activity will be terminated"
                    " after its work is finished. Looks like you forgot calling"
                    " `context.terminate()` in custom `on_activity_end` callback."
                )

            return work_result
