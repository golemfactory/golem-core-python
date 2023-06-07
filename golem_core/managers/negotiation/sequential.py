import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable, List, Optional, Sequence

from golem_core.core.golem_node.golem_node import DEFAULT_EXPIRATION_TIMEOUT, SUBNET, GolemNode
from golem_core.core.market_api import Demand, DemandBuilder, Payload, Proposal
from golem_core.core.market_api.resources.demand.demand_offer_base import defaults as dobm_defaults
from golem_core.core.market_api.resources.proposal import ProposalData
from golem_core.core.payment_api import Allocation
from golem_core.managers.base import ManagerException, NegotiationManager, NegotiationPlugin

logger = logging.getLogger(__name__)


class RejectProposal(Exception):
    pass


class SequentialNegotiationManager(NegotiationManager):
    def __init__(
        self,
        golem: GolemNode,
        get_allocation: Callable[[], Awaitable[Allocation]],
        payload: Payload,
        plugins: Optional[Sequence[NegotiationPlugin]] = None,
    ) -> None:
        self._golem = golem
        self._get_allocation = get_allocation
        self._payload = payload

        self._negotiation_loop_task: Optional[asyncio.Task] = None
        self._plugins: List[NegotiationPlugin] = list(plugins) if plugins is not None else []
        self._eligible_proposals: asyncio.Queue[Proposal] = asyncio.Queue()

    def register_plugin(self, plugin: NegotiationPlugin):
        self._plugins.append(plugin)

    def unregister_plugin(self, plugin: NegotiationPlugin):
        self._plugins.remove(plugin)

    async def get_proposal(self) -> Proposal:
        logger.debug("Getting proposal...")

        proposal = await self._eligible_proposals.get()

        logger.debug(f"Getting proposal done with `{proposal}`")

        return proposal

    async def start(self) -> None:
        logger.debug("Starting...")

        if self.is_started_started():
            message = "Already started!"
            logger.debug(f"Starting failed with `{message}`")
            raise ManagerException(message)

        self._negotiation_loop_task = asyncio.create_task(self._negotiation_loop(self._payload))

        logger.debug("Starting done")

    async def stop(self) -> None:
        logger.debug("Stopping...")

        if not self.is_started_started():
            message = "Already stopped!"
            logger.debug(f"Stopping failed with `{message}`")
            raise ManagerException(message)

        self._negotiation_loop_task.cancel()
        self._negotiation_loop_task = None

        logger.debug("Stopping done")

    def is_started_started(self) -> bool:
        return self._negotiation_loop_task is not None

    async def _negotiation_loop(self, payload: Payload) -> None:
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation, payload)

        demand = await demand_builder.create_demand(self._golem)
        demand.start_collecting_events()

        try:
            async for proposal in self._negotiate(demand):
                await self._eligible_proposals.put(proposal)
        finally:
            await demand.unsubscribe()

    async def _prepare_demand_builder(
        self, allocation: Allocation, payload: Payload
    ) -> DemandBuilder:
        logger.debug("Preparing demand...")

        # FIXME: Code looks duplicated as GolemNode.create_demand does the same

        demand_builder = DemandBuilder()

        await demand_builder.add(
            dobm_defaults.Activity(
                expiration=datetime.now(timezone.utc) + DEFAULT_EXPIRATION_TIMEOUT,
                multi_activity=True,
            )
        )
        await demand_builder.add(dobm_defaults.NodeInfo(subnet_tag=SUBNET))

        await demand_builder.add(payload)

        (
            allocation_properties,
            allocation_constraints,
        ) = await allocation.demand_properties_constraints()
        demand_builder.add_constraints(*allocation_constraints)
        demand_builder.add_properties({p.key: p.value for p in allocation_properties})

        logger.debug(f"Preparing demand done`")

        return demand_builder

    async def _negotiate(self, demand: Demand) -> AsyncIterator[Proposal]:
        demand_data = self._get_demand_data_from_demand(demand)

        async for initial_offer_proposal in demand.initial_proposals():
            offer_proposal = await self._negotiate_proposal(demand_data, initial_offer_proposal)

            if offer_proposal is None:
                logger.debug(
                    f"Negotiating proposal `{initial_offer_proposal}` done and proposal was rejected"
                )
                continue

            yield offer_proposal

    async def _negotiate_proposal(
        self, demand_builder: DemandBuilder, offer_proposal: Proposal
    ) -> Optional[Proposal]:
        logger.debug(f"Negotiating proposal `{offer_proposal}`...")

        while True:
            demand_builder_after_plugins = deepcopy(demand_builder)

            try:
                logger.debug(f"Applying plugins on `{offer_proposal}`...")

                for plugin in self._plugins:
                    demand_builder_after_plugins = await plugin(
                        demand_builder_after_plugins, offer_proposal
                    )

            except RejectProposal as e:
                logger.debug(
                    f"Applying plugins on `{offer_proposal}` done and proposal was rejected"
                )

                if not offer_proposal.initial:
                    await offer_proposal.reject(str(e))

                return None
            else:
                logger.debug(f"Applying plugins on `{offer_proposal}` done")

            if offer_proposal.initial or demand_builder_after_plugins != demand_builder:
                logger.debug("Sending demand proposal...")

                demand_proposal = await offer_proposal.respond(
                    demand_builder_after_plugins.properties,
                    demand_builder_after_plugins.constraints,
                )

                logger.debug("Sending demand proposal done")

                logger.debug("Waiting for response...")

                new_offer_proposal = await demand_proposal.responses().__anext__()

                logger.debug(f"Waiting for response done with `{new_offer_proposal}`")

                logger.debug(
                    f"Proposal `{offer_proposal}` received counter proposal `{new_offer_proposal}`"
                )
                offer_proposal = new_offer_proposal

                continue
            else:
                break

        logger.debug(f"Negotiating proposal `{offer_proposal}` done")

        return offer_proposal

    def _get_proposal_data_from_demand(self, demand: Demand) -> ProposalData:
        # FIXME: Unnecessary serialisation from DemandBuilder to Demand, and from Demand to ProposalData
        return ProposalData(demand.data.properties)
