import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

from prettytable import PrettyTable

from golem_api import GolemNode
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager
from golem_api.high.execute_tasks import default_prepare_activity
from golem_api.mid import (
    Buffer, Chain, Map, Zip,
    default_negotiate, default_create_agreement, default_create_activity,
)
from golem_api.low import PoolingBatch
from golem_api.events import NewResource

from yacat_no_business_logic import PAYLOAD, main_task_source, tasks_queue

MAX_CONCURRENT_NEGOTIATIONS = 10
MAX_CONCURRENT_TASKS = 1000

activity_queue = asyncio.Queue()
execution_time_log = defaultdict(list)


async def async_queue_aiter(src_queue: asyncio.Queue):
    while True:
        yield await src_queue.get()


async def filter_proposals(proposal_stream):
    for i in range(4):
        proposal = await proposal_stream.__anext__()
        print(proposal)
        yield proposal

    await asyncio.sleep(60)
    for i in range(4):
        proposal = await proposal_stream.__anext__()
        print(proposal)
        yield proposal

    await asyncio.Future()


async def close_agreement_repeat_task(func, args, e):
    activity, task = args
    tasks_queue.put_nowait(task)
    await activity.destroy()
    await activity.parent.terminate()


async def execute_task_return_activity(activity, task):
    await task.execute(activity)
    activity_queue.put_nowait(activity)


async def generate_activities(initial_proposal_generator):
    async for activity in Chain(
        initial_proposal_generator,
        filter_proposals,
        Map(default_negotiate),
        Map(default_create_agreement),
        Map(default_create_activity),
        Map(default_prepare_activity),
        Buffer(size=MAX_CONCURRENT_NEGOTIATIONS),
    ):
        activity_queue.put_nowait(activity)


async def execute_tasks():
    async for result in Chain(
        async_queue_aiter(activity_queue),
        Zip(async_queue_aiter(tasks_queue)),
        Map(execute_task_return_activity, on_exception=close_agreement_repeat_task),
        Buffer(size=MAX_CONCURRENT_TASKS),
    ):
        pass


async def gather_batch_log(event: NewResource):
    batch = event.resource
    start = datetime.now()
    provider_id = (await batch.parent.parent.parent.get_data()).issuer_id

    async def print_time():
        await batch.wait(ignore_errors=True)
        execution_time_log[provider_id].append(datetime.now() - start)

    asyncio.create_task(print_time())


async def print_current_data():
    while True:
        await asyncio.sleep(10)
        out = PrettyTable()
        out.field_names = ["provider_id", "batches", "total_time"]
        for provider_id, batches in execution_time_log.items():
            batch_cnt = len(batches)
            total_time = sum(batches, timedelta())
            out.add_row([provider_id, batch_cnt, total_time])

        print(out.get_string())


async def main() -> None:
    asyncio.create_task(main_task_source())
    asyncio.create_task(print_current_data())

    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)
    golem.event_bus.resource_listen(gather_batch_log, [NewResource], [PoolingBatch])

    async with golem:
        allocation = await golem.create_allocation(amount=1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        payment_manager = DefaultPaymentManager(golem, allocation)

        asyncio.create_task(generate_activities(demand.initial_proposals()))
        asyncio.create_task(execute_tasks())

        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            await payment_manager.terminate_agreements()
            await payment_manager.wait_for_invoices()

    #   TODO: This removes the "destroyed but pending" messages, probably there's
    #         some even prettier solution available?
    [task.cancel() for task in asyncio.all_tasks()]


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
