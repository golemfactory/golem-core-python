import asyncio
import logging
from copy import deepcopy
from datetime import datetime
from typing import AsyncIterator, Awaitable, Callable, List, Optional, Sequence, cast

from ya_market import ApiException

from golem.managers.base import (
    ManagerException,
    NegotiationManager,
    NegotiationPlugin,
    RejectProposal,
)
from golem.node import GolemNode
from golem.payload import Payload, Properties
from golem.payload.parsers.textx import TextXPayloadSyntaxParser
from golem.resources import Allocation, Demand, DemandBuilder, DemandData, Proposal, ProposalData
from golem.utils.asyncio import create_task_with_logging

logger = logging.getLogger(__name__)


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
        self._demand_offer_parser = TextXPayloadSyntaxParser()

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

        if self.is_started():
            message = "Already started!"
            logger.debug(f"Starting failed with `{message}`")
            raise ManagerException(message)

        self._negotiation_loop_task = create_task_with_logging(self._negotiation_loop())

        logger.debug("Starting done")

    async def stop(self) -> None:
        logger.debug("Stopping...")

        if not self.is_started():
            message = "Already stopped!"
            logger.debug(f"Stopping failed with `{message}`")
            raise ManagerException(message)

        self._negotiation_loop_task.cancel()
        self._negotiation_loop_task = None

        logger.debug("Stopping done")

    def is_started(self) -> bool:
        return self._negotiation_loop_task is not None and not self._negotiation_loop_task.done()

    async def _negotiation_loop(self) -> None:
        allocation = await self._get_allocation()
        demand_builder = await self._prepare_demand_builder(allocation)

        demand = await demand_builder.create_demand(self._golem)
        demand.start_collecting_events()

        logger.debug("Demand published, waiting for proposals...")

        try:
            async for proposal in self._negotiate(demand):
                await self._eligible_proposals.put(proposal)
        finally:
            await demand.unsubscribe()

    async def _prepare_demand_builder(self, allocation: Allocation) -> DemandBuilder:
        logger.debug("Preparing demand...")

        # FIXME: Code looks duplicated as GolemNode.create_demand does the same
        demand_builder = DemandBuilder()

        await demand_builder.add_default_parameters(
            self._demand_offer_parser, allocations=[allocation]
        )

        await demand_builder.add(self._payload)

        logger.debug("Preparing demand done")

        return demand_builder

    async def _negotiate(self, demand: Demand) -> AsyncIterator[Proposal]:
        demand_data = await self._get_demand_data_from_demand(demand)

        async for initial_proposal in demand.initial_proposals():
            offer_proposal = await self._negotiate_proposal(demand_data, initial_proposal)

            if offer_proposal is None:
                logger.debug(
                    f"Negotiating proposal `{initial_proposal}` done and proposal was rejected"
                )
                continue

            yield offer_proposal

    async def _negotiate_proposal(
        self, demand_data: DemandData, offer_proposal: Proposal
    ) -> Optional[Proposal]:
        logger.debug(f"Negotiating proposal `{offer_proposal}`...")

        while True:
            demand_data_after_plugins = deepcopy(demand_data)
            proposal_data = await self._get_proposal_data_from_proposal(offer_proposal)

            try:
                logger.debug(f"Applying plugins on `{offer_proposal}`...")

                for plugin in self._plugins:
                    plugin_result = plugin(demand_data_after_plugins, proposal_data)
                    if asyncio.iscoroutine(plugin_result):
                        plugin_result = await plugin_result
                    if isinstance(plugin_result, RejectProposal):
                        raise plugin_result
                    if plugin_result is False:
                        raise RejectProposal()

            except RejectProposal as e:
                logger.debug(
                    f"Applying plugins on `{offer_proposal}` done and proposal was rejected"
                )

                if not offer_proposal.initial:
                    await offer_proposal.reject(str(e))

                return None
            else:
                logger.debug(f"Applying plugins on `{offer_proposal}` done")

            if offer_proposal.initial or demand_data_after_plugins != demand_data:
                logger.debug("Sending demand proposal...")

                demand_data = demand_data_after_plugins

                try:
                    demand_proposal = await offer_proposal.respond(
                        demand_data_after_plugins.properties,
                        demand_data_after_plugins.constraints,
                    )
                except (ApiException, asyncio.TimeoutError) as e:
                    logger.debug(f"Sending demand proposal failed with `{e}`")
                    return None

                logger.debug("Sending demand proposal done")

                logger.debug("Waiting for response...")

                try:
                    new_offer_proposal = await demand_proposal.responses().__anext__()
                except StopAsyncIteration:
                    logger.debug("Waiting for response failed with rejection")
                    return None

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

    async def _get_demand_data_from_demand(self, demand: Demand) -> DemandData:
        # FIXME: Unnecessary serialisation from DemandBuilder to Demand,
        #  and from Demand to ProposalData
        data = await demand.get_data()

        constraints = self._demand_offer_parser.parse_constraints(data.constraints)

        return DemandData(
            properties=Properties(data.properties),
            constraints=constraints,
            demand_id=data.demand_id,
            requestor_id=data.requestor_id,
            timestamp=cast(datetime, data.timestamp),
        )

    async def _get_proposal_data_from_proposal(self, proposal: Proposal) -> ProposalData:
        data = await proposal.get_data()

        constraints = self._demand_offer_parser.parse_constraints(data.constraints)

        return ProposalData(
            properties=Properties(data.properties),
            constraints=constraints,
            proposal_id=data.proposal_id,
            issuer_id=data.issuer_id,
            state=data.state,
            timestamp=cast(datetime, data.timestamp),
            prev_proposal_id=data.prev_proposal_id,
        )
