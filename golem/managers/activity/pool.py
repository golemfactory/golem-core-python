import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from golem.managers.activity.mixins import ActivityPrepareReleaseMixin
from golem.managers.base import ActivityManager, Work, WorkContext, WorkResult
from golem.managers.mixins import BackgroundLoopMixin
from golem.node import GolemNode
from golem.resources import Agreement
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
        self._pool = asyncio.Queue()
        super().__init__(*args, **kwargs)

    async def _background_loop(self):
        pool_current_size = 0
        try:
            while True:
                if pool_current_size > self._pool_target_size:
                    # TODO check tasks results and add fallback
                    await asyncio.gather(
                        *[
                            self._release_activity_and_pop_from_pool()
                            for _ in range(pool_current_size - self._pool_target_size)
                        ]
                    )
                    pool_current_size -= pool_current_size - self._pool_target_size
                elif pool_current_size < self._pool_target_size:
                    # TODO check tasks results and add fallback
                    await asyncio.gather(
                        *[
                            self._prepare_activity_and_put_in_pool()
                            for _ in range(self._pool_target_size - pool_current_size)
                        ]
                    )
                    pool_current_size += self._pool_target_size - pool_current_size
                # TODO: Use events instead of sleep
                await asyncio.sleep(0.01)
        finally:
            logger.info(f"Releasing all {pool_current_size} activity from the pool")
            await asyncio.gather(
                *[self._release_activity_and_pop_from_pool() for _ in range(pool_current_size)]
            )

    @trace_span()
    async def _release_activity_and_pop_from_pool(self):
        activity = await self._pool.get()
        await self._release_activity(activity)
        logger.info(f"Activity `{activity}` removed from the pool")

    @trace_span()
    async def _prepare_activity_and_put_in_pool(self):
        agreement = await self._get_agreement()
        activity = await self._prepare_activity(agreement)
        await self._pool.put(activity)
        logger.info(f"Activity `{activity}` added to the pool")

    @asynccontextmanager
    async def _get_activity_from_pool(self):
        activity = await self._pool.get()
        logger.info(f"Activity `{activity}` taken from the pool")
        yield activity
        self._pool.put_nowait(activity)
        logger.info(f"Activity `{activity}` back in the pool")

    @trace_span()
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
