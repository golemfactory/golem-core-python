from datetime import timedelta
from typing import Dict, Iterable, Sequence, Tuple
from unittest.mock import AsyncMock

import pytest

from golem.managers import (
    LinearAverageCostPricing,
    MapScore,
    PropertyValueLerpScore,
    ProposalScoringMixin,
    Scorer,
)
from golem.payload import defaults


class FooBarProposalScorer(ProposalScoringMixin):
    ...


@pytest.mark.parametrize(
    "given_plugins, properties, expected_weights",
    (
        (
            [],
            ({} for _ in range(5)),
            [0.0, 0.0, 0.0, 0.0, 0.0],
        ),
        (
            (
                (
                    0.5,
                    PropertyValueLerpScore(defaults.INF_MEM, zero_at=1, one_at=5),
                ),
            ),
            ({defaults.INF_MEM: gib} for gib in range(7)),
            [1.0, 1.0, 0.75, 0.5, 0.25, 0.0, 0.0],
        ),
        (
            (
                (
                    1.0,
                    MapScore(
                        LinearAverageCostPricing(
                            average_cpu_load=1, average_duration=timedelta(seconds=60)
                        ),
                        normalize=True,
                        normalize_flip=True,
                    ),
                ),
            ),
            (
                {
                    "golem.com.pricing.model": "linear",
                    "golem.com.pricing.model.linear.coeffs": coeffs,
                }
                for coeffs in ([5e-05, 0.0001, 0.0], [5e-05, 0.0003, 0.0], [5e-05, 0.0002, 0.0])
            ),
            [1.0, 0.5, 0.0],
        ),
        (
            (
                (
                    1.0,
                    PropertyValueLerpScore(defaults.INF_MEM, zero_at=1, one_at=5),
                ),
                (
                    1.0,
                    MapScore(
                        LinearAverageCostPricing(
                            average_cpu_load=1, average_duration=timedelta(seconds=60)
                        ),
                        normalize=True,
                        normalize_flip=True,
                    ),
                ),
            ),
            (
                {
                    defaults.INF_MEM: gib,
                    "golem.com.pricing.model": "linear",
                    "golem.com.pricing.model.linear.coeffs": coeffs,
                }
                for gib, coeffs in (
                    (4, [5e-05, 0.0001, 0.0]),
                    (3, [5e-05, 0.0003, 0.0]),
                    (2, [5e-05, 0.0002, 0.0]),
                )
            ),
            [0.875, 0.375, 0.25],
        ),
    ),
)
async def test_weight_proposal_scoring_plugins_mixin_ok(
    yagna_proposal,
    given_plugins: Sequence[Tuple[float, Scorer]],
    properties: Iterable[Dict],
    expected_weights: Sequence[float],
):
    given_proposals = []
    for props in properties:
        proposal = AsyncMock()
        proposal.get_data.return_value = yagna_proposal(properties=props)
        given_proposals.append(proposal)

    scorer = FooBarProposalScorer(proposal_scorers=given_plugins)
    received_proposals = await scorer.do_scoring(given_proposals)
    assert expected_weights == [weight for weight, _ in received_proposals]
