import asyncio
import inspect
import logging
from datetime import datetime
from typing import Awaitable, Callable, List, Optional, Sequence, Tuple, cast

from golem.managers.base import (
    ManagerException,
    ManagerPluginsMixin,
    ProposalManager,
    ProposalManagerPluginWithOptionalWeight,
)
from golem.node import GolemNode
from golem.payload import Properties
from golem.payload.parsers.textx import TextXPayloadSyntaxParser
from golem.resources import Proposal, ProposalData
from golem.utils.asyncio import create_task_with_logging

logger = logging.getLogger(__name__)


class IgnoreProposal(Exception):
    pass


class ScoredAheadOfTimeProposalManager(
    ManagerPluginsMixin[ProposalManagerPluginWithOptionalWeight], ProposalManager
):
    def __init__(
        self, golem: GolemNode, get_proposal: Callable[[], Awaitable[Proposal]], *args, **kwargs
    ) -> None:
        self._get_proposal = get_proposal
        self._consume_proposals_task: Optional[asyncio.Task] = None
        self._demand_offer_parser = TextXPayloadSyntaxParser()

        self._scored_proposals: List[Tuple[float, Proposal]] = []
        self._scored_proposals_condition = asyncio.Condition()

        super().__init__(*args, **kwargs)

    async def start(self) -> None:
        logger.debug("Starting...")

        if self.is_started():
            message = "Already started!"
            logger.debug(f"Starting failed with `{message}`")
            raise ManagerException(message)

        self._consume_proposals_task = create_task_with_logging(self._consume_proposals())

        logger.debug("Starting done")

    async def stop(self) -> None:
        logger.debug("Stopping...")

        if not self.is_started():
            message = "Already stopped!"
            logger.debug(f"Stopping failed with `{message}`")
            raise ManagerException(message)

        self._consume_proposals_task.cancel()
        self._consume_proposals_task = None

        logger.debug("Stopping done")

    def is_started(self) -> bool:
        return self._consume_proposals_task is not None and not self._consume_proposals_task.done()

    async def _consume_proposals(self) -> None:
        while True:
            proposal = await self._get_proposal()

            logger.debug(f"Adding proposal `{proposal}` on the scoring...")

            async with self._scored_proposals_condition:
                all_proposals = list(sp[1] for sp in self._scored_proposals)
                all_proposals.append(proposal)

                self._scored_proposals = await self._do_scoring(all_proposals)

                self._scored_proposals_condition.notify_all()

            logger.debug(f"Adding proposal `{proposal}` on the scoring done")

    async def get_proposal(self) -> Proposal:
        logger.debug("Getting proposal...")

        async with self._scored_proposals_condition:
            await self._scored_proposals_condition.wait_for(lambda: 0 < len(self._scored_proposals))

            score, proposal = self._scored_proposals.pop(0)

        logger.debug(f"Getting proposal done with `{proposal}` with score `{score}`")

        logger.info(f"Proposal `{proposal}` picked")

        return proposal

    async def _do_scoring(self, proposals: Sequence[Proposal]):
        proposals_data = await self._get_proposals_data_from_proposals(proposals)
        proposal_scores = await self._run_plugins(proposals_data)

        scored_proposals = self._calculate_proposal_score(proposals, proposal_scores)
        scored_proposals.sort(key=lambda x: x[0], reverse=True)

        return scored_proposals

    async def _run_plugins(
        self, proposals_data: Sequence[ProposalData]
    ) -> Sequence[Tuple[float, Sequence[float]]]:
        proposal_scores = []

        for plugin in self._plugins:
            if isinstance(plugin, (list, tuple)):
                weight, plugin = plugin
            else:
                weight = 1

            plugin_scores = plugin(proposals_data)

            if inspect.isawaitable(plugin_scores):
                plugin_scores = await plugin_scores

            proposal_scores.append((weight, plugin_scores))

        return proposal_scores

    def _calculate_proposal_score(
        self,
        proposals: Sequence[Proposal],
        plugin_scores: Sequence[Tuple[float, Sequence[float]]],
    ) -> List[Tuple[float, Proposal]]:
        # FIXME: can this be refactored?
        return [
            (
                self._calculate_weighted_score(
                    self._transpose_plugin_scores(proposal_index, plugin_scores)
                ),
                proposal,
            )
            for proposal_index, proposal in enumerate(proposals)
        ]

    def _transpose_plugin_scores(
        self, proposal_index: int, plugin_scores: Sequence[Tuple[float, Sequence[float]]]
    ) -> Sequence[Tuple[float, float]]:
        # FIXME: can this be refactored?
        return [
            (plugin_weight, plugin_scores[proposal_index])
            for plugin_weight, plugin_scores in plugin_scores
            if plugin_scores[proposal_index] is None
        ]

    def _calculate_weighted_score(
        self, proposal_weighted_scores: Sequence[Tuple[float, float]]
    ) -> float:
        if not proposal_weighted_scores:
            return 0

        weighted_sum = sum(pws[0] * pws[1] for pws in proposal_weighted_scores)
        weights_sum = sum(pws[0] for pws in proposal_weighted_scores)

        return weighted_sum / weights_sum

    # FIXME: This should be already provided by low level
    async def _get_proposals_data_from_proposals(
        self, proposals: Sequence[Proposal]
    ) -> Sequence[ProposalData]:
        result = []

        for proposal in proposals:
            data = await proposal.get_data()

            constraints = self._demand_offer_parser.parse_constraints(data.constraints)

            result.append(
                ProposalData(
                    properties=Properties(data.properties),
                    constraints=constraints,
                    proposal_id=data.proposal_id,
                    issuer_id=data.issuer_id,
                    state=data.state,
                    timestamp=cast(datetime, data.timestamp),
                    prev_proposal_id=data.prev_proposal_id,
                )
            )

        return result
