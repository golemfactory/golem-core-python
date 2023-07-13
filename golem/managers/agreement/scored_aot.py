import asyncio
import inspect
import logging
from datetime import datetime
from typing import Awaitable, Callable, List, Sequence, Tuple, cast

from golem.managers.agreement.events import AgreementReleased
from golem.managers.base import (
    AgreementManager,
    ContextManagerLoopMixin,
    ManagerPluginsMixin,
    ManagerPluginWithOptionalWeight,
)
from golem.node import GolemNode
from golem.payload import Properties
from golem.payload.parsers.textx import TextXPayloadSyntaxParser
from golem.resources import Agreement, Proposal, ProposalData
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class ScoredAheadOfTimeAgreementManager(
    ContextManagerLoopMixin, ManagerPluginsMixin[ManagerPluginWithOptionalWeight], AgreementManager
):
    def __init__(
        self,
        golem: GolemNode,
        get_draft_proposal: Callable[[], Awaitable[Proposal]],
        *args,
        **kwargs,
    ):
        self._get_draft_proposal = get_draft_proposal
        self._event_bus = golem.event_bus

        self._demand_offer_parser = TextXPayloadSyntaxParser()

        self._scored_proposals: List[Tuple[float, Proposal]] = []
        self._scored_proposals_condition = asyncio.Condition()

        super().__init__(*args, **kwargs)

    async def _manager_loop(self) -> None:
        while True:
            proposal = await self._get_draft_proposal()

            await self._manage_scoring(proposal)

    @trace_span()
    async def _manage_scoring(self, proposal: Proposal) -> None:
        async with self._scored_proposals_condition:
            all_proposals = list(sp[1] for sp in self._scored_proposals)
            all_proposals.append(proposal)

            self._scored_proposals = await self._do_scoring(all_proposals)

            self._scored_proposals_condition.notify_all()

    @trace_span()
    async def _get_scored_proposal(self):
        async with self._scored_proposals_condition:
            await self._scored_proposals_condition.wait_for(lambda: 0 < len(self._scored_proposals))

            score, proposal = self._scored_proposals.pop(0)

        logger.info(f"Proposal `{proposal}` picked with score `{score}`")

        return proposal

    @trace_span()
    async def get_agreement(self) -> Agreement:
        while True:
            proposal = await self._get_scored_proposal()
            try:
                agreement = await proposal.create_agreement()
                await agreement.confirm()
                await agreement.wait_for_approval()
            except Exception as e:
                logger.debug(f"Creating agreement failed with `{e}`. Retrying...")
            else:
                logger.info(f"Agreement `{agreement}` created")

                # TODO: Support removing callback on resource close
                await self._event_bus.on_once(
                    AgreementReleased,
                    self._terminate_agreement,
                    lambda event: event.resource.id == agreement.id,
                )
                return agreement

    @trace_span()
    async def _terminate_agreement(self, event: AgreementReleased) -> None:
        agreement: Agreement = event.resource
        await agreement.terminate()
        logger.info(f"Agreement `{agreement}` closed")

    async def _do_scoring(self, proposals: Sequence[Proposal]):
        proposals_data = await self._get_proposals_data_from_proposals(proposals)
        proposal_scores = await self._run_plugins(proposals_data)

        scored_proposals = self._calculate_proposal_score(proposals, proposal_scores)
        scored_proposals.sort(key=lambda x: x[0], reverse=True)

        return scored_proposals

    @trace_span()
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
