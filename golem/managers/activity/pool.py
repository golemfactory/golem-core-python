import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from golem.managers.activity.mixins import ActivityPrepareReleaseMixin
from golem.managers.base import ActivityManager, Work, WorkContext, WorkResult
from golem.managers.mixins import BackgroundLoopMixin
from golem.node import GolemNode
from golem.resources import Activity, Agreement
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class ActivityPoolManager(BackgroundLoopMixin, ActivityPrepareReleaseMixin, ActivityManager):
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

        self._pool_target_size = size
        self._pool_current_size = 0
        self._pool: asyncio.Queue[Activity] = asyncio.Queue()
        super().__init__(*args, **kwargs)

    async def _background_loop(self):
        try:
            while True:
                if self._pool_current_size > self._pool_target_size:
                    # TODO check tasks results and add fallback
                    await asyncio.gather(
                        *[
                            self._release_activity_and_pop_from_pool()
                            for _ in range(self._pool_current_size - self._pool_target_size)
                        ]
                    )
                elif self._pool_current_size < self._pool_target_size:
                    # TODO check tasks results and add fallback
                    await asyncio.gather(
                        *[
                            self._prepare_activity_and_put_in_pool()
                            for _ in range(self._pool_target_size - self._pool_current_size)
                        ]
                    )
                # TODO: Use events instead of sleep
                await asyncio.sleep(0.01)
        finally:
            logger.info(f"Releasing all {self._pool_current_size} activity from the pool")
            # TODO cancel release adn prepare tasks
            await asyncio.gather(
                *[
                    self._release_activity_and_pop_from_pool()
                    for _ in range(self._pool_current_size)
                ]
            )

    @trace_span()
    async def _release_activity_and_pop_from_pool(self):
        activity = await self._pool.get()
        self._pool.task_done()
        self._pool_current_size -= 1
        await self._release_activity(activity)

    @trace_span()
    async def _prepare_activity_and_put_in_pool(self):
        agreement = await self._get_agreement()
        activity = await self._prepare_activity(agreement)
        await self._pool.put(activity)
        self._pool_current_size += 1

    @asynccontextmanager
    async def _get_activity_from_pool(self):
        activity = await self._pool.get()
        self._pool.task_done()
        logger.debug(f"Activity `{activity}` taken from the pool")
        try:
            yield activity
        finally:
            await self._pool.put(activity)
            logger.debug(f"Activity `{activity}` back in the pool")

    @trace_span(show_arguments=True, show_results=True)
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
