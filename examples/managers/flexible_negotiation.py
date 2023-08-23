import asyncio
import logging.config

from golem.managers import (
    ActivityPoolManager,
    AddChosenPaymentPlatform,
    BlacklistProviderIdPlugin,
    Buffer,
    DefaultAgreementManager,
    DefaultProposalManager,
    NegotiatingPlugin,
    PayAllPaymentManager,
    RefreshingDemandManager,
    SequentialWorkManager,
    WorkContext,
    WorkResult,
)
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING

BLACKLISTED_PROVIDERS = [
    "0x3b0f605fcb0690458064c10346af0c5f6b7202a5",
    "0x7ad8ce2f95f69be197d136e308303d2395e68379",
    "0x40f401ead13eabe677324bf50605c68caabb22c7",
]


async def commands_work_example(context: WorkContext) -> str:
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

    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    demand_manager = RefreshingDemandManager(golem, payment_manager.get_allocation, payload)

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
            NegotiatingPlugin(proposal_negotiators=[AddChosenPaymentPlatform()]),
            Buffer(
                min_size=3,
                max_size=5,
                concurrency_size=3,
            ),
        ],
    )

    agreement_manager = DefaultAgreementManager(golem, proposal_manager.get_draft_proposal)
    activity_manager = ActivityPoolManager(golem, agreement_manager.get_agreement, pool_size=3)
    work_manager = SequentialWorkManager(golem, activity_manager.do_work)

    async with golem:
        async with payment_manager, demand_manager, proposal_manager, agreement_manager, activity_manager:  # noqa: E501 line too long
            await asyncio.sleep(30)
            results: WorkResult = await work_manager.do_work(commands_work_example)
            print(f"\nWORK MANAGER RESULT:{results}\n")


if __name__ == "__main__":
    asyncio.run(main())
