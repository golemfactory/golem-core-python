import asyncio
import inspect
import logging
from datetime import datetime
from typing import Generic, List, Optional, Sequence, Tuple, cast

from golem.managers.base import ManagerException, ManagerPluginWithOptionalWeight, TPlugin
from golem.payload import Properties
from golem.payload.parsers.base import PayloadSyntaxParser
from golem.payload.parsers.textx.parser import TextXPayloadSyntaxParser
from golem.resources import Proposal, ProposalData
from golem.utils.asyncio import create_task_with_logging
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class BackgroundLoopMixin:
    def __init__(self, *args, **kwargs) -> None:
        self._background_loop_task: Optional[asyncio.Task] = None

        super().__init__(*args, **kwargs)

    @trace_span()
    async def start(self) -> None:
        if self.is_started():
            raise ManagerException("Already started!")

        self._background_loop_task = create_task_with_logging(self._background_loop())

    @trace_span()
    async def stop(self) -> None:
        if not self.is_started():
            raise ManagerException("Already stopped!")

        if self._background_loop_task is not None:
            self._background_loop_task.cancel()
            self._background_loop_task = None

    def is_started(self) -> bool:
        return self._background_loop_task is not None and not self._background_loop_task.done()

    async def _background_loop(self) -> None:
        pass


class ManagerPluginsMixin(Generic[TPlugin]):
    def __init__(self, plugins: Optional[Sequence[TPlugin]] = None, *args, **kwargs) -> None:
        self._plugins: List[TPlugin] = list(plugins) if plugins is not None else []

        super().__init__(*args, **kwargs)

    @trace_span()
    def register_plugin(self, plugin: TPlugin):
        self._plugins.append(plugin)

    @trace_span()
    def unregister_plugin(self, plugin: TPlugin):
        self._plugins.remove(plugin)


class WeightProposalScoringPluginsMixin(ManagerPluginsMixin[ManagerPluginWithOptionalWeight]):
    def __init__(
        self, demand_offer_parser: Optional[PayloadSyntaxParser] = None, *args, **kwargs
    ) -> None:
        self._demand_offer_parser = demand_offer_parser or TextXPayloadSyntaxParser()

        super().__init__(*args, **kwargs)

    async def do_scoring(self, proposals: Sequence[Proposal]) -> List[Tuple[float, Proposal]]:
        proposals_data = await self._get_proposals_data_from_proposals(proposals)
        proposal_scores = await self._run_plugins(proposals_data)

        scored_proposals = self._calculate_proposal_score(proposals, proposal_scores)
        scored_proposals.sort(key=lambda x: x[0], reverse=True)

        return scored_proposals

    @trace_span()
    async def _run_plugins(
        self, proposals_data: Sequence[ProposalData]
    ) -> Sequence[Tuple[float, Sequence[float]]]:
        proposal_scores: List[Tuple[float, Sequence[float]]] = []

        for plugin in self._plugins:
            if isinstance(plugin, (list, tuple)):
                weight, plugin = plugin
            else:
                weight = 1

            plugin_scores = plugin(proposals_data)

            if inspect.isawaitable(plugin_scores):
                plugin_scores = await plugin_scores

            proposal_scores.append((weight, plugin_scores))  # type: ignore[arg-type]

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

    def _calculate_weighted_score(
        self, proposal_weighted_scores: Sequence[Tuple[float, float]]
    ) -> float:
        if not proposal_weighted_scores:
            return 0

        weighted_sum = sum(pws[0] * pws[1] for pws in proposal_weighted_scores)
        weights_sum = sum(pws[0] for pws in proposal_weighted_scores)

        return weighted_sum / weights_sum

    def _transpose_plugin_scores(
        self, proposal_index: int, plugin_scores: Sequence[Tuple[float, Sequence[float]]]
    ) -> Sequence[Tuple[float, float]]:
        # FIXME: can this be refactored?
        return [
            (plugin_weight, plugin_scores[proposal_index])
            for plugin_weight, plugin_scores in plugin_scores
            if plugin_scores[proposal_index] is None
        ]

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
