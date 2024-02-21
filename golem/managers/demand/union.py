import asyncio
import logging
from typing import Awaitable, Callable, MutableMapping, Optional, Sequence

from golem.managers import DemandManager
from golem.node import GolemNode
from golem.resources import Proposal
from golem.utils.asyncio import create_task_with_logging, ensure_cancelled_many
from golem.utils.logging import trace_span


class UnionDemandManager(DemandManager):
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

    @trace_span("Stopping UnionDemandManager", log_level=logging.INFO)
    async def stop(self) -> None:
        await ensure_cancelled_many(self._task_map.values())
        self._task_map.clear()

    @trace_span("Getting initial proposal", show_results=True)
    async def get_initial_proposal(self) -> Proposal:
        """Call and return first completed Proposal from `get_initial_proposal_funcs`.

        `get_initial_proposal_funcs` will be called concurrently, where not returned results will
        be saved and returned with the next call. If no proposals are saved, and some other
        functions are pending, completed functions will be run again. In case of multiple proposals
        are saved, they will be returned in declaration order of `get_initial_proposal_funcs`.
        """
        async with self._lock:
            proposal = self._get_ready_proposal()
            if proposal:
                return proposal

            for func in self._get_initial_proposal_funcs:
                if func not in self._task_map:
                    self._task_map[func] = create_task_with_logging(func())

            await asyncio.wait(self._task_map.values(), return_when=asyncio.FIRST_COMPLETED)

            proposal = self._get_ready_proposal()
            assert proposal
            return proposal

    def _get_ready_proposal(self) -> Optional[Proposal]:
        for func, task in self._task_map.items():
            if task.done():
                del self._task_map[func]
                return task.result()

        return None
