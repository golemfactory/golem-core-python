import asyncio
import logging.config
from random import randint
from typing import List

from golem.managers import (
    AddChosenPaymentPlatform,
    DefaultAgreementManager,
    PayAllPaymentManager,
    RefreshingDemandManager,
    SequentialNegotiationManager,
    SequentialWorkManager,
    SingleUseActivityManager,
    WorkContext,
    WorkResult,
)
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING


async def commands_work_example(context: WorkContext) -> str:
    r = await context.run("echo 'hello golem'")
    await r.wait()
    result = ""
    for event in r.events:
        result += event.stdout
    return result


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
    demand_manager = RefreshingDemandManager(golem, payment_manager.get_allocation, payload)
    negotiation_manager = SequentialNegotiationManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            AddChosenPaymentPlatform(),
        ],
    )
    agreement_manager = DefaultAgreementManager(golem, negotiation_manager.get_draft_proposal)
    activity_manager = SingleUseActivityManager(golem, agreement_manager.get_agreement)
    work_manager = SequentialWorkManager(golem, activity_manager.do_work)

    async with golem:
        async with payment_manager, demand_manager, negotiation_manager, agreement_manager:
            results: List[WorkResult] = await work_manager.do_work_list(work_list)
            print(f"\nWORK MANAGER RESULTS:{[result.result for result in results]}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
