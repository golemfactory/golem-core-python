import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from golem.managers.activity.mixins import ActivityPrepareReleaseMixin
from golem.managers.base import ActivityManager, Work, WorkContext, WorkResult
from golem.node import GolemNode
from golem.resources import Agreement
from golem.utils.asyncio import create_task_with_logging

logger = logging.getLogger(__name__)


class ActivityPoolManager(ActivityPrepareReleaseMixin, ActivityManager):
    def __init__(
        self,
        golem: GolemNode,
        get_agreement: Callable[[], Awaitable[Agreement]],
        size: int,
        *args,
        **kwargs,
    ):
        self._get_agreement = get_agreement
        self._event_bus = golem.event_bus

        self._pool_size = size
        self._pool = asyncio.Queue(maxsize=self._pool_size)
        super().__init__(*args, **kwargs)

    async def start(self):
        for _ in range(self._pool_size):
            create_task_with_logging(self._prepare_activity_and_put_in_pool())

    async def _prepare_activity_and_put_in_pool(self):
        agreement = await self._get_agreement()
        activity = await self._prepare_activity(agreement)
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
