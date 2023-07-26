import asyncio
import random
from datetime import timedelta
from typing import Dict, Iterable, Optional, Sequence, Tuple
from unittest.mock import AsyncMock

import pytest

from golem.managers import (
    BackgroundLoopMixin,
    LinearAverageCostPricing,
    Manager,
    ManagerScorePlugin,
    MapScore,
    PropertyValueLerpScore,
    WeightProposalScoringPluginsMixin,
)
from golem.payload import defaults


class FooBarBackgroundLoopManager(BackgroundLoopMixin, Manager):
    def __init__(self, foo: int, *args, **kwargs) -> None:
        self.foo: int = foo
        self.bar: Optional[int] = None

        super().__init__(*args, **kwargs)

    async def _background_loop(self) -> None:
        self.bar = self.foo
        while True:
            # await to switch out of the loop
            await asyncio.sleep(1)


async def test_background_loop_mixin_ok():
    given_bar = random.randint(0, 10)
    manager = FooBarBackgroundLoopManager(given_bar)
    assert not manager.is_started()
    assert manager.bar is None
    async with manager:
        # await to switch to `FooBarBackgroundLoopManager._background_loop`
        await asyncio.sleep(0.1)
        assert manager.is_started()
        assert manager.bar == given_bar
    assert not manager.is_started()
    assert manager.bar == given_bar


class FooBarWeightProposalScoringPluginsManager(WeightProposalScoringPluginsMixin, Manager):
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
    given_plugins: Sequence[Tuple[float, ManagerScorePlugin]],
    properties: Iterable[Dict],
    expected_weights: Sequence[float],
):
    given_proposals = []
    for props in properties:
        proposal = AsyncMock()
        proposal.get_data.return_value = yagna_proposal(properties=props)
        given_proposals.append(proposal)

    manager = FooBarWeightProposalScoringPluginsManager(plugins=given_plugins)
    received_proposals = await manager.do_scoring(given_proposals)
    assert expected_weights == [weight for weight, _ in received_proposals]
