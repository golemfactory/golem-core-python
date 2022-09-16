import asyncio
from datetime import timedelta
from random import random
from typing import AsyncIterator, AsyncGenerator, TypeVar

from yapapi.payload import vm

from golem_api import GolemNode, commands
from golem_api.low import Activity, DebitNote, Invoice, Proposal

from golem_api.mid import Chain, SimpleScorer, DefaultNegotiator, AgreementCreator, ActivityCreator
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager
from golem_api.events import NewResource


IMAGE_HASH = "9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae"
X = TypeVar('X')


async def score_proposal(proposal: Proposal) -> float:
    return random()


async def max_3(any_generator: AsyncIterator[X]) -> AsyncGenerator[X, None]:
    #   This function can be inserted anywhere in the example chain
    #   (except as the first element)
    cnt = 0
    async for x in any_generator:
        yield x
        cnt += 1
        if cnt == 3:
            break


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1)

        payment_manager = DefaultPaymentManager(allocation)
        golem.event_bus.resource_listen(payment_manager.on_invoice, [NewResource], [Invoice])
        golem.event_bus.resource_listen(payment_manager.on_debit_note, [NewResource], [DebitNote])

        payload = await vm.repo(image_hash=IMAGE_HASH)
        demand = await golem.create_demand(payload, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=1)),
            DefaultNegotiator(buffer_size=5),
            AgreementCreator(),
            ActivityCreator(),
            max_3,
        )
        activity: Activity
        async for activity in chain:
            print(f"--> {activity}")
            batch = await activity.execute_commands(
                commands.Deploy(),
                commands.Start(),
                commands.Run("/bin/echo", ["hello", "world"]),
                commands.Run("/bin/sleep", ["5"]),
            )
            await batch.finished
            for event in batch.events:
                print("STDOUT", event.stdout)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    task = loop.create_task(main())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
