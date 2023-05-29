import asyncio
from datetime import datetime
import logging.config

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.core.market_api import RepositoryVmPayload
from golem_core.managers.activity.single_use import SingleUseActivityManager
from golem_core.managers.agreement.single_use import SingleUseAgreementManager
from golem_core.managers.base import WorkContext
from golem_core.managers.negotiation import AlfaNegotiationManager
from golem_core.managers.offer import StackOfferManager
from golem_core.managers.payment.pay_all import PayAllPaymentManager
from golem_core.managers.work.sequential import SequentialWorkManager
from golem_core.utils.logging import DEFAULT_LOGGING


async def work1(context: WorkContext):
    r = await context.run("echo 1")
    await r.wait()
    result = ""
    for event in r.events:
        print(event.stdout)
        result += event.stdout
    return result


async def work2(context: WorkContext):
    r = await context.run("echo 2")
    await r.wait()
    for event in r.events:
        print(event.stdout)


async def work3(context: WorkContext):
    r = await context.run("echo 3")
    await r.wait()
    for event in r.events:
        print(event.stdout)


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

    work_list = [
        work1,
        # work2,
        # work3,
    ]

    async with GolemNode() as golem:
        payment_manager = PayAllPaymentManager(golem, budget=1.0)
        negotiation_manager = AlfaNegotiationManager(golem, payment_manager.get_allocation)
        offer_manager = StackOfferManager(negotiation_manager.get_offer)
        agreement_manager = SingleUseAgreementManager(offer_manager.get_offer, golem.event_bus)
        activity_manager = SingleUseActivityManager(
            agreement_manager.get_agreement, golem.event_bus
        )
        work_manager = SequentialWorkManager(activity_manager.do_work)

        await negotiation_manager.start_negotiation(payload)
        await offer_manager.start_consuming_offers()

        print("starting to work...")
        results = await work_manager.do_work_list(work_list)
        print("work done")
        print(results)

        print(f"{datetime.utcnow()} stopping example...")
        await offer_manager.stop_consuming_offers()
        await negotiation_manager.stop_negotiation()

        # TODO wait for invoices and debit notes
        for _ in range(20):
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
