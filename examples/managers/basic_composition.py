import asyncio
import logging.config
from datetime import timedelta
from random import randint, random
from typing import List

from golem.managers.activity.single_use import SingleUseActivityManager
from golem.managers.agreement.plugins import MapScore, PropertyValueLerpScore, RandomScore
from golem.managers.agreement.pricings import LinearAverageCostPricing
from golem.managers.agreement.scored_aot import ScoredAheadOfTimeAgreementManager
from golem.managers.base import RejectProposal, WorkContext, WorkResult
from golem.managers.demand.auto import AutoDemandManager
from golem.managers.negotiation import SequentialNegotiationManager
from golem.managers.negotiation.plugins import (
    AddChosenPaymentPlatform,
    BlacklistProviderId,
    RejectIfCostsExceeds,
)
from golem.managers.payment.pay_all import PayAllPaymentManager
from golem.managers.work.plugins import redundancy_cancel_others_on_first_done, retry, work_plugin
from golem.managers.work.sequential import SequentialWorkManager
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.payload.defaults import INF_MEM
from golem.resources.demand.demand import DemandData
from golem.resources.proposal.proposal import ProposalData
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


async def commands_work_example(context: WorkContext) -> str:
    r = await context.run("echo 'hello golem'")
    await r.wait()
    result = ""
    for event in r.events:
        result += event.stdout
    return result


@work_plugin(redundancy_cancel_others_on_first_done(size=2))
async def batch_work_example(context: WorkContext):
    if randint(0, 1):
        raise Exception("Random fail")
    batch = await context.create_batch()
    batch.run("echo 'hello batch'")
    batch.run("echo 'bye batch'")
    batch_result = await batch()
    result = ""
    for event in batch_result:
        result += event.stdout
    return result


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

    work_list = [
        commands_work_example,
        batch_work_example,
    ]

    golem = GolemNode()

    linear_average_cost = LinearAverageCostPricing(
        average_cpu_load=0.2, average_duration=timedelta(seconds=5)
    )

    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    demand_manager = AutoDemandManager(
        golem,
        payment_manager.get_allocation,
        payload,
    )
    negotiation_manager = SequentialNegotiationManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            AddChosenPaymentPlatform(),
            # class based plugin
            BlacklistProviderId(BLACKLISTED_PROVIDERS),
            RejectIfCostsExceeds(1, linear_average_cost),
            # func plugin
            blacklist_func,
            # lambda plugin
            lambda _, proposal_data: proposal_data.issuer_id not in BLACKLISTED_PROVIDERS,
            # lambda plugin with reject reason
            lambda _, proposal_data: RejectProposal(f"Blacklisting {proposal_data.issuer_id}")
            if proposal_data.issuer_id in BLACKLISTED_PROVIDERS
            else None,
        ],
    )
    agreement_manager = ScoredAheadOfTimeAgreementManager(
        golem,
        negotiation_manager.get_draft_proposal,
        plugins=[
            MapScore(linear_average_cost, normalize=True, normalize_flip=True),
            [0.5, PropertyValueLerpScore(INF_MEM, zero_at=1, one_at=8)],
            [0.1, RandomScore()],
            [0.0, lambda proposals_data: [random() for _ in range(len(proposals_data))]],
            [0.0, MapScore(lambda proposal_data: random())],
        ],
    )
    activity_manager = SingleUseActivityManager(golem, agreement_manager.get_agreement)
    work_manager = SequentialWorkManager(
        golem,
        activity_manager.do_work,
        plugins=[
            retry(tries=5),
        ],
    )

    async with golem:
        async with payment_manager, demand_manager, negotiation_manager, agreement_manager:
            results: List[WorkResult] = await work_manager.do_work_list(work_list)
            print(f"\nWORK MANAGER RESULTS:{[result.result for result in results]}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
