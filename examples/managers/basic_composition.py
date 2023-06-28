import asyncio
import logging.config
from random import randint
from typing import List, Optional

from golem.managers.activity.single_use import SingleUseActivityManager
from golem.managers.agreement.single_use import SingleUseAgreementManager
from golem.managers.base import RejectProposal, WorkContext, WorkResult
from golem.managers.negotiation import SequentialNegotiationManager
from golem.managers.negotiation.plugins import AddChosenPaymentPlatform, BlacklistProviderId
from golem.managers.payment.pay_all import PayAllPaymentManager
from golem.managers.proposal import StackProposalManager
from golem.managers.work.decorators import (
    redundancy_cancel_others_on_first_done,
    retry,
    work_decorator,
)
from golem.managers.work.sequential import SequentialWorkManager
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.resources.demand.demand import DemandData
from golem.resources.proposal.proposal import ProposalData
from golem.utils.logging import DEFAULT_LOGGING

BLACKLISTED_PROVIDERS = [
    "0x3b0f605fcb0690458064c10346af0c5f6b7202a5",
    "0x7ad8ce2f95f69be197d136e308303d2395e68379",
    "0x40f401ead13eabe677324bf50605c68caabb22c7",
]


async def blacklist_func(
    demand_data: DemandData, proposal_data: ProposalData
) -> Optional[RejectProposal]:
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


@work_decorator(redundancy_cancel_others_on_first_done(size=2))
@work_decorator(retry(tries=5))
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

    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    negotiation_manager = SequentialNegotiationManager(
        golem,
        payment_manager.get_allocation,
        payload,
        plugins=[
            AddChosenPaymentPlatform(),
            # class based plugin
            BlacklistProviderId(BLACKLISTED_PROVIDERS),
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
    proposal_manager = StackProposalManager(golem, negotiation_manager.get_proposal)
    agreement_manager = SingleUseAgreementManager(golem, proposal_manager.get_proposal)
    activity_manager = SingleUseActivityManager(golem, agreement_manager.get_agreement)
    work_manager = SequentialWorkManager(golem, activity_manager.do_work)

    async with golem:
        async with payment_manager, negotiation_manager, proposal_manager:
            results: List[WorkResult] = await work_manager.do_work_list(work_list)
            print(f"\nWORK MANAGER RESULTS:{[result.result for result in results]}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
