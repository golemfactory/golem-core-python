import asyncio
import logging.config
from datetime import timedelta
from random import randint, random

from golem.managers import (
    AddChosenPaymentPlatform,
    BlacklistProviderIdNegotiator,
    BlacklistProviderIdPlugin,
    Buffer,
    DefaultAgreementManager,
    DefaultProposalManager,
    LinearAverageCostPricing,
    MapScore,
    NegotiatingPlugin,
    PayAllPaymentManager,
    PoolActivityManager,
    PropertyValueLerpScore,
    RandomScore,
    RefreshingDemandManager,
    RejectIfCostsExceeds,
    RejectProposal,
    ScoringBuffer,
    SequentialWorkManager,
    WorkContext,
    WorkResult,
    redundancy_cancel_others_on_first_done,
    retry,
    work_plugin,
)
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload, defaults
from golem.resources import DemandData, ProposalData
from golem.utils.logging import DEFAULT_LOGGING

BLACKLISTED_PROVIDERS = [
    "0x3b0f605fcb0690458064c10346af0c5f6b7202a5",
    "0x7ad8ce2f95f69be197d136e308303d2395e68379",
    "0x40f401ead13eabe677324bf50605c68caabb22c7",
]


async def blacklist_func(demand_data: DemandData, proposal_data: ProposalData) -> None:
    provider_id = proposal_data.issuer_id
    if provider_id in BLACKLISTED_PROVIDERS:
        raise RejectProposal(f"Provider ID `{provider_id}` is blacklisted by the requestor")


@work_plugin(redundancy_cancel_others_on_first_done(size=2))
async def commands_work_example(context: WorkContext) -> str:
    if randint(0, 1):
        raise Exception("Random fail")
    r = await context.run("echo 'hello golem'")
    await r.wait()
    result = ""
    for event in r.events:
        result += event.stdout
    return result


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

    golem = GolemNode()

    linear_average_cost = LinearAverageCostPricing(
        average_cpu_load=0.2, average_duration=timedelta(seconds=5)
    )

    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    demand_manager = RefreshingDemandManager(
        golem,
        payment_manager.get_allocation,
        payload,
    )
    proposal_manager = DefaultProposalManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            Buffer(
                min_size=10,
                max_size=1000,
                concurrency_size=5,
            ),
            BlacklistProviderIdPlugin(BLACKLISTED_PROVIDERS),
            NegotiatingPlugin(
                proposal_negotiators=[
                    AddChosenPaymentPlatform(),
                    # class based plugin
                    BlacklistProviderIdNegotiator(BLACKLISTED_PROVIDERS),
                    RejectIfCostsExceeds(1, linear_average_cost),
                    # func plugin
                    blacklist_func,  # type: ignore[list-item]
                    # lambda plugin
                    lambda _, proposal_data: proposal_data.issuer_id  # type: ignore[list-item]
                    not in BLACKLISTED_PROVIDERS,
                    # lambda plugin with reject reason
                    lambda _, proposal_data: RejectProposal(  # type: ignore[list-item]
                        f"Blacklisting {proposal_data.issuer_id}"
                    )
                    if proposal_data.issuer_id in BLACKLISTED_PROVIDERS
                    else None,
                ]
            ),
            ScoringBuffer(
                min_size=3,
                max_size=5,
                concurrency_size=3,
                proposal_scorers=[
                    # List of Scorer or Tuple[float, Scorer], float in [-1,1] range
                    MapScore(linear_average_cost, normalize=True, normalize_flip=True),
                    [0.5, PropertyValueLerpScore(defaults.INF_MEM, zero_at=1, one_at=8)],
                    [0.1, RandomScore()],
                    [0.0, lambda proposals_data: [random() for _ in range(len(proposals_data))]],
                    [0.0, MapScore(lambda proposal_data: random())],
                ],
            ),
        ],
    )
    agreement_manager = DefaultAgreementManager(
        golem,
        proposal_manager.get_draft_proposal,
    )
    activity_manager = PoolActivityManager(golem, agreement_manager.get_agreement, pool_size=3)
    work_manager = SequentialWorkManager(
        golem,
        activity_manager.get_activity,
        plugins=[
            retry(tries=5),
        ],
    )

    async with golem:
        async with payment_manager, demand_manager, proposal_manager, agreement_manager, activity_manager:  # noqa: E501 line too long
            await asyncio.sleep(10)
            result: WorkResult = await work_manager.do_work(commands_work_example)
            print(f"\nWORK MANAGER RESULT:{result}\n")


if __name__ == "__main__":
    asyncio.run(main())
