import inspect
from datetime import datetime
from typing import List, Optional, Sequence, Tuple, cast

from golem.managers.base import ScorerWithOptionalWeight
from golem.payload import PayloadSyntaxParser, Properties
from golem.resources import Proposal, ProposalData
from golem.utils.logging import trace_span


class ProposalScoringMixin:
    def __init__(
        self,
        proposal_scorers: Optional[Sequence[ScorerWithOptionalWeight]] = None,
        *args,
        **kwargs,
    ) -> None:
        self._demand_offer_parser = PayloadSyntaxParser.get_instance()
        self._proposal_scorers: List[ScorerWithOptionalWeight] = (
            list(proposal_scorers) if proposal_scorers is not None else []
        )

        super().__init__(*args, **kwargs)

    async def do_scoring(self, proposals: Sequence[Proposal]) -> List[Tuple[float, Proposal]]:
        proposals_data = await self._get_proposals_data_from_proposals(proposals)
        proposal_scores = await self._run_scorers(proposals_data)

        scored_proposals = self._calculate_proposal_score(proposals, proposal_scores)
        scored_proposals.sort(key=lambda x: x[0], reverse=True)

        return scored_proposals

    @trace_span()
    async def _run_scorers(
        self, proposals_data: Sequence[ProposalData]
    ) -> Sequence[Tuple[float, Sequence[float]]]:
        proposal_scores: List[Tuple[float, Sequence[float]]] = []

        for scorer in self._proposal_scorers:
            if isinstance(scorer, (list, tuple)):
                weight, scorer = scorer
            else:
                weight = 1

            scorer_scores = scorer(proposals_data)

            if inspect.isawaitable(scorer_scores):
                scorer_scores = await scorer_scores

            proposal_scores.append((weight, scorer_scores))  # type: ignore[arg-type]

        return proposal_scores

    def _calculate_proposal_score(
        self,
        proposals: Sequence[Proposal],
        scorer_scores: Sequence[Tuple[float, Sequence[float]]],
    ) -> List[Tuple[float, Proposal]]:
        # FIXME: can this be refactored?
        return [
            (
                self._calculate_weighted_score(
                    self._transpose_scorer_scores(proposal_index, scorer_scores)
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

    def _transpose_scorer_scores(
        self, proposal_index: int, scorer_scores: Sequence[Tuple[float, Sequence[float]]]
    ) -> Sequence[Tuple[float, float]]:
        # FIXME: can this be refactored?
        return [
            (scorer_weight, scorer_scores[proposal_index])
            for scorer_weight, scorer_scores in scorer_scores
            if scorer_scores[proposal_index] is not None
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
