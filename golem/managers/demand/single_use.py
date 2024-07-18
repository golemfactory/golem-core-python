import logging
from itertools import chain
from typing import Awaitable, Callable, Sequence

from golem.managers.base import DemandManager
from golem.managers.mixins import BackgroundLoopMixin
from golem.node import GolemNode
from golem.payload import Payload
from golem.payload import defaults as payload_defaults
from golem.resources import Allocation, Demand, Proposal
from golem.resources.demand.demand_builder import DemandBuilder
from golem.utils.asyncio import ErrorReportingQueue
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class SingleUseDemandManager(BackgroundLoopMixin, DemandManager):
    """DemandManager that creates one single demand as a single source of initial proposals."""

    def __init__(
        self,
        golem: GolemNode,
        get_allocation: Callable[[], Awaitable[Allocation]],
        payloads: Sequence[Payload],
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._payloads = payloads

        self._initial_proposals: ErrorReportingQueue[Proposal] = ErrorReportingQueue()

        super().__init__()

    @trace_span("Starting SingleUseDemandManager", log_level=logging.INFO)
    async def start(self) -> None:
        return await super().start()

    @trace_span("Stopping SingleUseDemandManager", log_level=logging.INFO)
    async def stop(self) -> None:
        return await super().stop()

    @trace_span("Getting initial proposal", show_results=True)
    async def get_initial_proposal(self) -> Proposal:
        proposal = await self._initial_proposals.get()
        self._initial_proposals.task_done()
        return proposal

    @trace_span()
    async def _background_loop(self) -> None:
        demand = await self._create_and_subscribe_demand()
        demand.start_collecting_events()

        try:
            await self._consume_initial_proposals(demand)
        except Exception as e:
            self._initial_proposals.set_exception(e)
            logger.debug(
                "Encountered unexpected exception while handling demands,"
                " exception is set and background loop will be stopped!"
            )
        finally:
            await demand.unsubscribe()

    @trace_span()
    async def _create_and_subscribe_demand(self):
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation)
        logger.debug(f"Creating demand: {demand_builder=}")
        demand = await demand_builder.create_demand(self._golem)

        return demand

    @trace_span()
    async def _prepare_demand_builder(self, allocation: Allocation) -> DemandBuilder:
        # FIXME: Code looks duplicated as GolemNode.create_demand does the same
        demand_builder = DemandBuilder()

        for demand_spec in chain(
            [
                payload_defaults.ActivityInfo(
                    lifetime=payload_defaults.DEFAULT_LIFETIME, multi_activity=True
                ),
                payload_defaults.PaymentInfo(),
                await allocation.get_demand_spec(),
            ],
            self._payloads,
        ):
            await demand_builder.add(demand_spec)

        return demand_builder

    @trace_span()
    async def _consume_initial_proposals(self, demand: Demand):
        initial_proposals_gen = demand.initial_proposals()
        first_initial_proposal = await initial_proposals_gen.__anext__()
        logger.info("Received first initial proposal")

        logger.debug(f"New initial proposal {first_initial_proposal}")
        self._initial_proposals.put_nowait(first_initial_proposal)

        async for initial in initial_proposals_gen:
            logger.debug(f"New initial proposal {initial}")
            self._initial_proposals.put_nowait(initial)
