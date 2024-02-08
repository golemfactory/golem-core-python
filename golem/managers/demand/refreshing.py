import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List, Tuple

from golem.managers.base import DemandManager
from golem.managers.mixins import BackgroundLoopMixin
from golem.node import GolemNode
from golem.payload import Payload
from golem.payload import defaults as payload_defaults
from golem.resources import Allocation, Demand, Proposal
from golem.resources.demand.demand_builder import DemandBuilder
from golem.utils.asyncio import ErrorReportingQueue, create_task_with_logging, ensure_cancelled_many
from golem.utils.logging import get_trace_id_name, trace_span

logger = logging.getLogger(__name__)


class RefreshingDemandManager(BackgroundLoopMixin, DemandManager):
    def __init__(
        self,
        golem: GolemNode,
        get_allocation: Callable[[], Awaitable[Allocation]],
        payloads: List[Payload],
        demand_lifetime: timedelta = payload_defaults.DEFAULT_LIFETIME,
        subnet_tag: str = payload_defaults.DEFAULT_SUBNET,
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._payloads = payloads
        self._demand_lifetime = demand_lifetime
        self._subnet_tag = subnet_tag

        self._initial_proposals: ErrorReportingQueue[Proposal] = ErrorReportingQueue()

        self._demands: List[Tuple[Demand, asyncio.Task]] = []
        super().__init__()

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
        try:
            while True:
                if self._demands:
                    await self._wait_for_demand_to_expire()
                    await self._stop_consuming_initial_proposals()

                await self._create_and_subscribe_demand()
        except Exception as e:
            self._initial_proposals.set_exception(e)
            logger.debug(
                "Encountered unexpected exception while handling demands,"
                " exception is set and background loop will be stopped!"
            )
        finally:
            await self._stop_consuming_initial_proposals()
            await self._unsubscribe_demands()

    async def _wait_for_demand_to_expire(self):
        await self._demands[-1][0].get_data()
        expiration_date = await self._demands[-1][0].get_expiration_date()
        remaining = expiration_date - datetime.now(timezone.utc)
        await asyncio.sleep(remaining.total_seconds())

    @trace_span()
    async def _create_and_subscribe_demand(self):
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation)
        logger.debug(f"Creating demand: {demand_builder=}")
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
    async def _stop_consuming_initial_proposals(self) -> None:
        await ensure_cancelled_many([d[1] for d in self._demands])

    @trace_span()
    async def _prepare_demand_builder(self, allocation: Allocation) -> DemandBuilder:
        # FIXME: Code looks duplicated as GolemNode.create_demand does the same
        demand_builder = DemandBuilder()

        for demand_spec in [
            payload_defaults.ActivityInfo(lifetime=self._demand_lifetime, multi_activity=True),
            payload_defaults.NodeInfo(subnet_tag=self._subnet_tag),
            payload_defaults.PaymentInfo(),
            await allocation.get_demand_spec(),
        ] + self._payloads:
            await demand_builder.add(demand_spec)

        return demand_builder

    @trace_span()
    async def _unsubscribe_demands(self):
        results = await asyncio.gather(
            *[demand.unsubscribe() for demand, _ in self._demands], return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Unable to unsubscribe demand due to {type(result)}:\n{result}")
