import asyncio
import logging
from typing import Awaitable, Callable

from golem.managers.activity.mixins import ActivityPrepareReleaseMixin, ActivityWrapper
from golem.managers.base import ActivityManager
from golem.managers.mixins import BackgroundLoopMixin
from golem.node import GolemNode
from golem.resources import Activity, Agreement
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


@Activity.register
class PoolActivity(ActivityWrapper):
    def __init__(self, activity, put_activity_to_pool_func) -> None:
        super().__init__(activity)
        self._put_activity_to_pool_func = put_activity_to_pool_func

    async def destroy(self) -> None:
        await self._put_activity_to_pool_func(self._activity)


class PoolActivityManager(BackgroundLoopMixin, ActivityPrepareReleaseMixin, ActivityManager):
    def __init__(
        self,
        golem: GolemNode,
        get_agreement: Callable[[], Awaitable[Agreement]],
        pool_size: int,
        *args,
        **kwargs,
    ):
        self._get_agreement = get_agreement
        self._event_bus = golem.event_bus

        self._pool_target_size = pool_size
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
                            self._prepare_activity_and_put_to_pool()
                            for _ in range(self._pool_target_size - self._pool_current_size)
                        ]
                    )
                # TODO: Use events instead of sleep
                await asyncio.sleep(0.01)
        finally:
            logger.info(f"Releasing all {self._pool_current_size} activities from the pool")
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
    async def _prepare_activity_and_put_to_pool(self):
        agreement = await self._get_agreement()
        activity = await self._prepare_activity(agreement)
        await self._pool.put(activity)
        self._pool_current_size += 1

    async def _get_activity_from_pool(self):
        activity = await self._pool.get()
        self._pool.task_done()
        logger.debug(f"Activity `{activity}` taken from the pool")
        return activity

    async def _put_activity_to_pool(self, activity):
        await self._pool.put(activity)
        logger.debug(f"Activity `{activity}` back to the pool")

    @trace_span(show_arguments=True, show_results=True)
    async def get_activity(self) -> Activity:
        activity = await self._get_activity_from_pool()
        # mypy doesn't support `ABCMeta.register` https://github.com/python/mypy/issues/2922
        return PoolActivity(activity, self._put_activity_to_pool)  # type: ignore[return-value]
