import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, Optional

from golem.managers.activity.defaults import default_on_activity_start, default_on_activity_stop
from golem.managers.agreement import AgreementReleased
from golem.managers.base import ActivityManager, Work, WorkContext, WorkResult
from golem.node import GolemNode
from golem.resources import Activity, Agreement
from golem.utils.asyncio import create_task_with_logging

logger = logging.getLogger(__name__)


class ActivityPoolManager(ActivityManager):  # TODO ActivityPrepeareReleaseMixin
    def __init__(
        self,
        golem: GolemNode,
        get_agreement: Callable[[], Awaitable[Agreement]],
        size: int,
        on_activity_start: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_start,
        on_activity_stop: Optional[
            Callable[[WorkContext], Awaitable[None]]
        ] = default_on_activity_stop,
    ):
        self._get_agreement = get_agreement
        self._event_bus = golem.event_bus
        self._on_activity_start = on_activity_start
        self._on_activity_stop = on_activity_stop

        self._pool_size = size
        self._pool = asyncio.Queue(maxsize=self._pool_size)

    async def start(self):
        for _ in range(self._pool_size):
            create_task_with_logging(self._prepare_activity_and_put_in_pool())

    async def _prepare_activity_and_put_in_pool(self):
        activity = await self._prepare_activity()
        await self._pool.put(activity)
        logger.info(f"Activity `{activity}` added to the pool")

    async def stop(self):
        await asyncio.gather(
            *[
                create_task_with_logging(self._release_activity(await self._pool.get()))
                for _ in range(self._pool_size)
            ]
        )
        assert self._pool.empty()

    async def _prepare_activity(self) -> Activity:
        agreement = await self._get_agreement()
        activity = await agreement.create_activity()
        logger.info(f"Activity `{activity}` created")
        work_context = WorkContext(activity)
        if self._on_activity_start:
            await self._on_activity_start(work_context)
        return activity

    async def _release_activity(self, activity: Activity) -> None:
        if self._on_activity_stop:
            work_context = WorkContext(activity)
            await self._on_activity_stop(work_context)

        if activity.destroyed:
            logger.info(f"Activity `{activity}` destroyed")
        else:
            logger.warning(
                "ActivityPoolManager expects that activity will be terminated"
                " before activity is released. Looks like you forgot calling"
                " `context.terminate()` in custom `on_activity_end` callback."
            )

        event = AgreementReleased(activity.parent)
        await self._event_bus.emit(event)

    @asynccontextmanager
    async def _get_activity_from_pool(self):
        activity = await self._pool.get()
        logger.info(f"Activity `{activity}` taken from the pool")
        yield activity
        self._pool.put_nowait(activity)
        logger.info(f"Activity `{activity}` back in the pool")

    async def do_work(self, work: Work) -> WorkResult:
        async with self._get_activity_from_pool() as activity:
            work_context = WorkContext(activity)
            try:
                work_result = await work(work_context)
            except Exception as e:
                work_result = WorkResult(exception=e)
            else:
                if not isinstance(work_result, WorkResult):
                    work_result = WorkResult(result=work_result)
        return work_result
