import asyncio
import logging.config

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import RepositoryVmPayload
from golem_core.managers.activity.single_use import SingleUseActivityManager
from golem_core.managers.agreement.single_use import SingleUseAgreementManager
from golem_core.managers.base import WorkContext
from golem_core.managers.negotiation import AcceptAllNegotiationManager
from golem_core.managers.payment.pay_all import PayAllPaymentManager
from golem_core.managers.proposal import StackProposalManager
from golem_core.managers.work.sequential import SequentialWorkManager
from golem_core.utils.logging import DEFAULT_LOGGING


async def work1(context: WorkContext):
    r = await context.run("echo 1")
    await r.wait()
    result = ""
    for event in r.events:
        print(f"Work1 got: {event.stdout}")
        result += event.stdout
    return result


async def work2(context: WorkContext):
    r = await context.run("echo 2")
    await r.wait()
    result = ""
    for event in r.events:
        print(f"Work2 got: {event.stdout}")
        result += event.stdout
    return result


async def work3(context: WorkContext):
    r = await context.run("echo 3")
    await r.wait()
    result = ""
    for event in r.events:
        print(f"Work3 got: {event.stdout}")
        result += event.stdout
    return result


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

    work_list = [
        work1,
        work2,
        work3,
    ]

    async with GolemNode() as golem:
        payment_manager = PayAllPaymentManager(golem, budget=1.0)
        negotiation_manager = AcceptAllNegotiationManager(golem, payment_manager.get_allocation)
        proposal_manager = StackProposalManager(negotiation_manager.get_proposal)
        agreement_manager = SingleUseAgreementManager(
            proposal_manager.get_proposal, golem.event_bus
        )
        activity_manager = SingleUseActivityManager(
            agreement_manager.get_agreement, golem.event_bus
        )
        work_manager = SequentialWorkManager(activity_manager.do_work)

        await negotiation_manager.start_negotiation(payload)
        await proposal_manager.start_consuming_proposals()

        results = await work_manager.do_work_list(work_list)
        print(f"work done: {results}")

        await proposal_manager.stop_consuming_proposals()
        await negotiation_manager.stop_negotiation()
        await payment_manager.wait_for_invoices()


if __name__ == "__main__":
    asyncio.run(main())
