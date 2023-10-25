import asyncio
import logging
import logging.config
from typing import List

from golem.managers import (
    AddChosenPaymentPlatform,
    DefaultAgreementManager,
    DefaultProposalManager,
    NegotiatingPlugin,
    PayAllPaymentManager,
    RefreshingDemandManager,
    SequentialWorkManager,
    SingleUseActivityManager,
    WorkContext,
    WorkResult,
)
from golem.managers.base import ProposalManagerPlugin
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.resources import Proposal
from golem.utils.logging import DEFAULT_LOGGING

logger = logging.getLogger(__name__)

PROVIDERS_WHITELIST = ["0x98730f729471410db10f4d4951fb9f7c35aaac70"]


class WhitelistPlugin(ProposalManagerPlugin):
    def __init__(self, whitelist: List[str]) -> None:
        self._whitelist = whitelist

    async def get_proposal(self) -> Proposal:
        while True:
            proposal: Proposal = await self._get_proposal()
            proposal_data = await proposal.get_data()
            provider_id = proposal_data.issuer_id

            if provider_id in self._whitelist:
                print(f"Found provider from the whitelist {provider_id}")
                return proposal

            if not proposal.initial:
                await proposal.reject("provider_id is not on whitelist")


async def hello_golem(context: WorkContext) -> str:
    r = await context.run("echo 'hello golem'")
    await r.wait()
    result = ""
    for event in r.events:
        result += event.stdout
    return result


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload("07195fdd1b104831e9e56e4fc24cfb536df37cabf3e63953c01f108e")

    golem = GolemNode()

    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    demand_manager = RefreshingDemandManager(golem, payment_manager.get_allocation, payload)
    proposal_manager = DefaultProposalManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            WhitelistPlugin(PROVIDERS_WHITELIST),
            NegotiatingPlugin(proposal_negotiators=[AddChosenPaymentPlatform()]),
        ],
    )
    agreement_manager = DefaultAgreementManager(golem, proposal_manager.get_draft_proposal)
    activity_manager = SingleUseActivityManager(golem, agreement_manager.get_agreement)
    work_manager = SequentialWorkManager(golem, activity_manager.get_activity)

    async with golem:
        async with payment_manager, demand_manager, proposal_manager, agreement_manager:
            result: WorkResult = await work_manager.do_work(hello_golem)
            print(f"\nWORK MANAGER RESULT:{result.result}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
