import asyncio
from collections import defaultdict

from prettytable import PrettyTable

from golem_api import GolemNode
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager
from golem_api.high.execute_tasks import default_prepare_activity
from golem_api.mid import (
    Buffer, Chain, Map, Zip,
    default_negotiate, default_create_agreement, default_create_activity,
)
from golem_api.low import DebitNote, PoolingBatch, Activity
from golem_api.events import NewResource, ResourceClosed

from yacat_no_business_logic import PAYLOAD, main_task_source, tasks_queue, results

MAX_CONCURRENT_NEGOTIATIONS = 10
MAX_CONCURRENT_TASKS = 1000
MAX_GLM_PER_RESULT = 0.00092
NEW_PERIOD_SECONDS = 600

activity_queue = asyncio.Queue()
activity_data = defaultdict(lambda: dict(batch_cnt=0, glm=0, status="new"))


async def async_queue_aiter(src_queue: asyncio.Queue):
    while True:
        yield await src_queue.get()


async def filter_proposals(proposal_stream):
    for i in range(15):
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


async def gather_execution_time_log(event: NewResource):
    activity = event.resource.parent
    activity_data[activity]['batch_cnt'] += 1


async def gather_debit_note_log(event: NewResource):
    debit_note = event.resource
    activity_id = (await debit_note.get_data()).activity_id
    activity = debit_note.node.activity(activity_id)
    current_glm = activity_data[activity]['glm']
    new_glm = max(current_glm, float(debit_note.data.total_amount_due))
    activity_data[activity]['glm'] = new_glm


async def note_activity_destroyed(event: ResourceClosed):
    activity = event.resource
    current_status = activity_data[activity]['status']
    if current_status in ('new', 'ok'):
        activity_data[activity]['status'] = 'Dead [unknown reason]'


async def print_current_data():
    while True:
        await asyncio.sleep(15)
        try:
            _print_summary_table()
        except Exception as e:
            print(e)


async def update_new_activity_status(event: NewResource):
    activity = event.resource

    async def set_ok_status():
        await asyncio.sleep(NEW_PERIOD_SECONDS)
        if activity_data[activity]['status'] == 'new':
            activity_data[activity]['status'] = 'ok'
    asyncio.create_task(set_ok_status())


async def manage_activities():
    while True:
        await asyncio.sleep(5)
        summary_data = _get_summary_data()
        too_expensive = summary_data[-1][3] > MAX_GLM_PER_RESULT
        if too_expensive:
            ok_activities = {activity: data for activity, data in activity_data.items() if data['status'] == 'ok'}
            if ok_activities:
                most_expensive = max(
                    ok_activities,
                    key=lambda activity: ok_activities[activity]['glm'] / ok_activities[activity]['batch_cnt']
                )
                await most_expensive.destroy()
                activity_data[most_expensive]['status'] = 'Dead [too expensive]'
                await most_expensive.parent.terminate()


async def main() -> None:
    asyncio.create_task(main_task_source())
    asyncio.create_task(print_current_data())
    asyncio.create_task(manage_activities())

    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)
    golem.event_bus.resource_listen(gather_execution_time_log, [NewResource], [PoolingBatch])
    golem.event_bus.resource_listen(gather_debit_note_log, [NewResource], [DebitNote])
    golem.event_bus.resource_listen(update_new_activity_status, [NewResource], [Activity])
    golem.event_bus.resource_listen(note_activity_destroyed, [ResourceClosed], [Activity])

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


def _print_summary_table():
    agg_data = _get_summary_data()
    table = PrettyTable()
    table.field_names = [
        "activity_id", "results", "GLM", "GLM/result", "batches", "GLM/batch", f"> {MAX_GLM_PER_RESULT}", "status"
    ]
    table.add_rows(agg_data)
    print(table.get_string())


def _get_summary_data():
    total_results = len(results)
    total_batches = sum(data['batch_cnt'] for data in activity_data.values())
    total_glm = sum(data['glm'] for data in activity_data.values())

    batch_result_ratio = total_batches / total_results if total_results else 0
    glm_result_ratio = total_glm / total_results if total_results else 0
    glm_batch_ratio = total_glm / total_batches if total_batches else 0

    agg_data = []
    for activity, data in activity_data.items():
        activity_batches, activity_glm, activity_status = data['batch_cnt'], data['glm'], data['status']
        activity_results = activity_batches / batch_result_ratio if batch_result_ratio else 0
        activity_glm_result_ratio = round(activity_glm / activity_results, 6) if activity_results else 0
        agg_data.append([
            activity.id,
            round(activity_results, 2),
            round(activity_glm, 6),
            activity_glm_result_ratio,
            activity_batches,
            round(activity_glm / activity_batches, 6),
            "X" if activity_glm_result_ratio > MAX_GLM_PER_RESULT else "",
            activity_status,
        ])

    agg_data.append([
        'TOTAL',
        total_results,
        round(total_glm, 6),
        round(glm_result_ratio, 6),
        total_batches,
        round(glm_batch_ratio, 6),
        "X" if glm_result_ratio > MAX_GLM_PER_RESULT else "",
        "",
    ])
    return agg_data


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
