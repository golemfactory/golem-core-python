import asyncio
import logging.config
from contextlib import asynccontextmanager

from golem_core.core.golem_node import GolemNode
from golem_core.core.market_api import RepositoryVmPayload
from golem_core.managers.activity import SingleUseActivityManager
from golem_core.managers.agreement.single_use import SingleUseAgreementManager
from golem_core.managers.base import WorkContext
from golem_core.managers.work import SequentialWorkManager
from golem_core.utils.logging import DEFAULT_LOGGING


@asynccontextmanager
async def create_proposal():
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

    print("Entering golem context...")
    async with GolemNode() as golem:
        print("Creating allocation...")
        allocation = await golem.create_allocation(1)
        print("Creating demand...")
        demand = await golem.create_demand(payload, allocations=[allocation])

        print("Gathering initial proposals...")
        async for proposal in demand.initial_proposals():
            print("Responding to initial proposal...")
            try:
                our_response = await proposal.respond()
            except Exception as e:
                print(str(e))
                continue

            print("Waiting for initial proposal...")
            try:
                their_response = await our_response.responses().__anext__()
            except StopAsyncIteration:
                continue

            yield golem, their_response

            # print('Creating agreement...')
            # agreement = await their_response.create_agreement()
            # await agreement.confirm()
            # await agreement.wait_for_approval()

            # print('Yielding agreement...')
            # yield agreement
            # return


async def work1(context: WorkContext):
    r = await context.run("echo 1")
    await r.wait()
    for event in r.events:
        print(event.stdout, flush=True)


async def work2(context: WorkContext):
    r = await context.run("echo 2")
    await r.wait()
    for event in r.events:
        print(event.stdout, flush=True)


async def work3(context: WorkContext):
    r = await context.run("echo 3")
    await r.wait()
    for event in r.events:
        print(event.stdout, flush=True)


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)

    async with create_proposal() as (golem, proposal):
        async def get_proposal():
            return proposal

        work_list = [
            work1,
            # work2,
            # work3,
        ]

        agreement_manager = SingleUseAgreementManager(get_proposal, golem.event_bus)

        activity_manager = SingleUseActivityManager(
            agreement_manager.get_agreement,
            golem.event_bus,
        )

        work_manager = SequentialWorkManager(activity_manager.do_work)

        print("starting to work...")
        results = await work_manager.do_work_list(work_list)
        print("work done")
        print(results)
        print("sleeping...")
        await asyncio.sleep(10)
        print("sleeping done")


if __name__ == "__main__":
    asyncio.run(main())
