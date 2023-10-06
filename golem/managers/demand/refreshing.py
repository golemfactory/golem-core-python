import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List, Optional, Tuple

from golem.managers.base import DemandManager
from golem.managers.mixins import BackgroundLoopMixin
from golem.node import GolemNode
from golem.payload import Payload, PayloadSyntaxParser
from golem.resources import Allocation, Demand, Proposal
from golem.resources.demand.demand_builder import DemandBuilder
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


class RefreshingDemandManager(BackgroundLoopMixin, DemandManager):
    def __init__(
        self,
        golem: GolemNode,
        get_allocation: Callable[[], Awaitable[Allocation]],
        payload: Payload,
        demand_expiration_timeout: timedelta = timedelta(minutes=30),
        demand_offer_parser: Optional[PayloadSyntaxParser] = None,
        *args,
        **kwargs,
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._payload = payload
        self._demand_expiration_timeout = demand_expiration_timeout

        if demand_offer_parser is None:
            from golem.payload.parsers.textx import TextXPayloadSyntaxParser

            demand_offer_parser = TextXPayloadSyntaxParser()

        self._demand_offer_parser = demand_offer_parser

        self._initial_proposals: asyncio.Queue[Proposal] = asyncio.Queue()

        self._demands: List[Tuple[Demand, asyncio.Task]] = []
        super().__init__(*args, **kwargs)

    @trace_span("Starting RefreshingDemandManager", log_level=logging.INFO)
    async def start(self) -> None:
        return await super().start()

    @trace_span("Stopping RefreshingDemandManager", log_level=logging.INFO)
    async def stop(self) -> None:
        return await super().stop()

    @trace_span("Getting initial proposal", show_results=True)
    async def get_initial_proposal(self) -> Proposal:
        proposal = await self._initial_proposals.get()
        self._initial_proposals.task_done()
        return proposal

    @trace_span()
    async def _background_loop(self) -> None:
        await self._create_and_subscribe_demand()
        try:
            while True:
                await self._wait_for_demand_to_expire()
                self._stop_consuming_initial_proposals()
                await self._create_and_subscribe_demand()
        finally:
            self._stop_consuming_initial_proposals()
            await self._unsubscribe_demands()

    async def _wait_for_demand_to_expire(self):
        remaining: timedelta = (
            datetime.utcfromtimestamp(
                self._demands[-1][0].data.properties["golem.srv.comp.expiration"] / 1000
            )
            - datetime.utcnow()
        )
        await asyncio.sleep(remaining.seconds)

    @trace_span()
    async def _create_and_subscribe_demand(self):
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation)
        demand = await demand_builder.create_demand(self._golem)
        demand.start_collecting_events()
        await demand.get_data()
        self._demands.append(
            (
                demand,
                create_task_with_logging(
                    self._consume_initial_proposals(demand),
                    trace_id=get_trace_id_name(self, f"demand-{demand.id}-proposal-consumer-loop"),
                ),
            )
        )

    @trace_span()
    async def _consume_initial_proposals(self, demand: Demand):
        try:
            initial_proposals_gen = demand.initial_proposals()
            first_initial_proposal = await initial_proposals_gen.__anext__()
            logger.info("Received first initial proposal")

            logger.debug(f"New initial proposal {first_initial_proposal}")
            self._initial_proposals.put_nowait(first_initial_proposal)

            async for initial in initial_proposals_gen:
                logger.debug(f"New initial proposal {initial}")
                self._initial_proposals.put_nowait(initial)
        except asyncio.CancelledError:
            pass

    @trace_span()
    def _stop_consuming_initial_proposals(self) -> List[bool]:
        return [d[1].cancel() for d in self._demands]

    @trace_span()
    async def _prepare_demand_builder(self, allocation: Allocation) -> DemandBuilder:
        # FIXME: Code looks duplicated as GolemNode.create_demand does the same
        demand_builder = DemandBuilder()

        await demand_builder.add_default_parameters(
            self._demand_offer_parser,
            allocations=[allocation],
            expiration=datetime.now(timezone.utc) + self._demand_expiration_timeout,
        )

        await demand_builder.add(self._payload)

        return demand_builder

    @trace_span()
    async def _unsubscribe_demands(self):
        await asyncio.gather(*[demand.unsubscribe() for demand, _ in self._demands])
