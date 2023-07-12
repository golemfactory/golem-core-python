import asyncio
import logging
from copy import deepcopy
from datetime import datetime
from typing import AsyncIterator, Awaitable, Callable, Optional, cast

from ya_market import ApiException

from golem.managers.base import (
    ManagerException,
    ManagerPluginsMixin,
    NegotiationManager,
    NegotiationManagerPlugin,
    RejectProposal,
)
from golem.node import GolemNode
from golem.payload import Properties
from golem.payload.parsers.textx import TextXPayloadSyntaxParser
from golem.resources import Allocation, DemandData, Proposal, ProposalData
from golem.utils.asyncio import create_task_with_logging

logger = logging.getLogger(__name__)


class SequentialNegotiationManager(
    ManagerPluginsMixin[NegotiationManagerPlugin], NegotiationManager
):
    # TODO remove unused methods
    def __init__(
        self,
        golem: GolemNode,
        get_initial_proposal: Callable[[], Awaitable[Allocation]],
        *args,
        **kwargs,
    ) -> None:
        self._golem = golem
        self._get_initial_proposal = get_initial_proposal

        self._negotiation_loop_task: Optional[asyncio.Task] = None
        self._eligible_proposals: asyncio.Queue[Proposal] = asyncio.Queue()
        self._demand_offer_parser = TextXPayloadSyntaxParser()

        super().__init__(*args, **kwargs)

    async def get_draft_proposal(self) -> Proposal:
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
        while True:  # TODO add buffer
            proposal = await self._get_initial_proposal()
            offer_proposal = await self._negotiate(proposal)
            if offer_proposal is not None:
                await self._eligible_proposals.put(offer_proposal)

    async def _negotiate(self, initial_proposal: Proposal) -> AsyncIterator[Proposal]:
        demand_data = await self._get_demand_data_from_proposal(initial_proposal)

        offer_proposal = await self._negotiate_proposal(demand_data, initial_proposal)

        if offer_proposal is None:
            logger.debug(
                f"Negotiating proposal `{initial_proposal}` done and proposal was rejected"
            )
            return

        return offer_proposal

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

                    # Note: Explicit identity to False desired here, not "falsy" check
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
                    logger.debug("Waiting for response failed with provider rejection")
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

    async def _get_demand_data_from_proposal(self, proposal: Proposal) -> DemandData:
        # FIXME: Unnecessary serialisation from DemandBuilder to Demand,
        #  and from Demand to ProposalData
        data = await proposal.demand.get_data()

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
