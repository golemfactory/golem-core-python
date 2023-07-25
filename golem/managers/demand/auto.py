import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable, List, MutableSequence, Sequence, Tuple

from golem.managers.base import DemandManager
from golem.managers.mixins import BackgroundLoopMixin, WeightProposalScoringPluginsMixin
from golem.node import GolemNode
from golem.payload import Payload
from golem.resources import Allocation, Demand, Proposal
from golem.resources.demand.demand_builder import DemandBuilder
from golem.utils.asyncio import create_task_with_logging
from golem.utils.buffer import ConcurrentlyFilledBuffer
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class AutoDemandManager(BackgroundLoopMixin, WeightProposalScoringPluginsMixin, DemandManager):
    def __init__(
        self,
        golem: GolemNode,
        get_allocation: Callable[[], Awaitable[Allocation]],
        payload: Payload,
        *args,
        **kwargs,
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._payload = payload

        self._initial_proposals: asyncio.Queue = asyncio.Queue()
        self._buffer = ConcurrentlyFilledBuffer(
            fill_callback=self._initial_proposals.get,
            min_size=1,
            max_size=1000,
            update_callback=self._update_buffer_callback,
            update_interval=timedelta(seconds=1),
        )

        self._demands: List[Tuple[Demand, asyncio.Task]] = []
        super().__init__(*args, **kwargs)

    @trace_span(show_results=True)
    async def get_initial_proposal(self) -> Proposal:
        return await self._buffer.get_item()

    @trace_span()
    async def _background_loop(self) -> None:
        await self._buffer.start()
        await self._create_and_subscribe_demand()
        try:
            while True:
                if datetime.utcfromtimestamp(
                    self._demands[-1][0].data.properties["golem.srv.comp.expiration"] / 1000
                ) < datetime.utcnow() + timedelta(minutes=29, seconds=50):
                    self._stop_consuming_initial_proposals()
                    await self._create_and_subscribe_demand()
                await asyncio.sleep(0.5)
        finally:
            self._stop_consuming_initial_proposals()
            await self._buffer.stop()
            await self._unsubscribe_demands()

    async def _update_buffer_callback(
        self, items: MutableSequence[Proposal], items_to_process: Sequence[Proposal]
    ) -> None:
        items.extend(items_to_process)
        items = [proposal for _, proposal in await self.do_scoring(items)]

    @trace_span()
    async def _create_and_subscribe_demand(self):
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation)
        demand = await demand_builder.create_demand(self._golem)
        demand.start_collecting_events()
        await demand.get_data()
        self._demands.append(
            (demand, create_task_with_logging(self._consume_initial_proposals(demand)))
        )

    @trace_span()
    async def _consume_initial_proposals(self, demand: Demand):
        try:
            async for initial in demand.initial_proposals():
                logger.debug(f"New initial proposal {initial}")
                self._initial_proposals.put_nowait(initial)
        except asyncio.CancelledError:
            ...

    @trace_span()
    def _stop_consuming_initial_proposals(self) -> List[bool]:
        return [d[1].cancel() for d in self._demands]

    @trace_span()
    async def _prepare_demand_builder(self, allocation: Allocation) -> DemandBuilder:
        # FIXME: Code looks duplicated as GolemNode.create_demand does the same
        demand_builder = DemandBuilder()

        await demand_builder.add_default_parameters(
            self._demand_offer_parser, allocations=[allocation]
        )

        await demand_builder.add(self._payload)

        return demand_builder

    @trace_span()
    async def _unsubscribe_demands(self):
        await asyncio.gather(*[demand.unsubscribe() for demand, _ in self._demands])
