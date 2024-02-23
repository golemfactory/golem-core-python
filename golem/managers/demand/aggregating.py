import asyncio
import logging
from typing import Awaitable, Callable, MutableMapping, Sequence

from golem.managers import DemandManager
from golem.node import GolemNode
from golem.resources import Proposal
from golem.utils.asyncio import create_task_with_logging, ensure_cancelled_many
from golem.utils.logging import trace_span


class AggregatingDemandManager(DemandManager):
    """DemandManager that combines multiple get_initial_proposal functions into one."""

    def __init__(
        self,
        golem: GolemNode,
        get_initial_proposal_funcs: Sequence[Callable[[], Awaitable[Proposal]]],
    ) -> None:
        self._golem = golem
        self._get_initial_proposal_funcs = get_initial_proposal_funcs

        self._lock = asyncio.Lock()

        self._task_map: MutableMapping[Callable[[], Awaitable[Proposal]], asyncio.Task] = {}

        self._queue: asyncio.Queue[Proposal] = asyncio.Queue()

    @trace_span("Stopping AggregatingDemandManager", log_level=logging.INFO)
    async def stop(self) -> None:
        await ensure_cancelled_many(self._task_map.values())
        self._task_map.clear()

    @trace_span("Getting initial proposal", show_results=True)
    async def get_initial_proposal(self) -> Proposal:
        """Call and return first completed Proposal from `get_initial_proposal_funcs`.

        `get_initial_proposal_funcs` will be called concurrently, where not returned results will
        be saved and returned with the next call. If no proposals are saved, and some other
        functions are pending, completed functions will be run again. In case of multiple proposals
        are saved, they will be returned in completion  order.
        """

        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        async with self._lock:
            for func in self._get_initial_proposal_funcs:
                if func not in self._task_map:
                    self._task_map[func] = create_task_with_logging(self._feed_queue(func))

        return await self._queue.get()

    async def _feed_queue(self, func: Callable[[], Awaitable[Proposal]]):
        proposal = await func()
        self._queue.put_nowait(proposal)

        async with self._lock:
            del self._task_map[func]
