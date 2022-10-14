import asyncio
from collections import defaultdict

from prettytable import PrettyTable

from golem_api import GolemNode
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager
from golem_api.high.execute_tasks import default_prepare_activity, default_score_proposal
from golem_api.mid import (
    Buffer, Chain, Map, Zip,
    ActivityPool, SimpleScorer,
    default_negotiate, default_create_agreement, default_create_activity,
)
from golem_api.low import DebitNote, PoolingBatch, Activity
from golem_api.events import NewResource, ResourceClosed

from yacat_no_business_logic import PAYLOAD, main_task_source, tasks_queue, results

MAX_CONCURRENT_TASKS = 1000
MAX_GLM_PER_RESULT = 0.00097
NEW_PERIOD_SECONDS = 400
MAX_WORKERS = 10

activity_data = defaultdict(lambda: dict(batch_cnt=0, last_dn_batch_cnt=0, glm=0, status="new"))


async def async_queue_aiter(src_queue: asyncio.Queue):
    while True:
        yield await src_queue.get()


async def close_agreement_repeat_task(func, args, e):
    activity, task = args
    tasks_queue.put_nowait(task)
    await activity.destroy()
    await activity.parent.terminate()


async def count_batches(event: NewResource):
    activity = event.resource.parent
    activity_data[activity]['batch_cnt'] += 1


async def gather_debit_note_log(event: NewResource):
    debit_note = event.resource
    activity_id = (await debit_note.get_data()).activity_id
    activity = debit_note.node.activity(activity_id)
    current_glm = activity_data[activity]['glm']
    new_glm = max(current_glm, float(debit_note.data.total_amount_due))
    activity_data[activity]['glm'] = new_glm
    activity_data[activity]['last_dn_batch_cnt'] = activity_data[activity]['batch_cnt']


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
        ok_activities = {activity: data for activity, data in activity_data.items() if data['status'] == 'ok'}
        if not ok_activities:
            continue

        summary_data = _get_summary_data(list(ok_activities))
        too_expensive = summary_data[-1][3] > MAX_GLM_PER_RESULT
        if not too_expensive:
            continue

        print("SUMMARY DATA", summary_data)
        print(f"TOO EXPENSIVE - target: {MAX_GLM_PER_RESULT}, current 'ok' activities: {summary_data[-1][3]}")

        most_expensive = max(
            ok_activities,
            key=lambda activity: ok_activities[activity]['glm'] / ok_activities[activity]['batch_cnt']
        )
        print(f"Stopping {most_expensive} because it's most expensive")
        await most_expensive.destroy()
        activity_data[most_expensive]['status'] = 'Dead [too expensive]'
        await most_expensive.parent.terminate()


async def main() -> None:
    asyncio.create_task(main_task_source())
    asyncio.create_task(print_current_data())
    asyncio.create_task(manage_activities())

    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)
    golem.event_bus.resource_listen(count_batches, [NewResource], [PoolingBatch])
    golem.event_bus.resource_listen(gather_debit_note_log, [NewResource], [DebitNote])
    golem.event_bus.resource_listen(update_new_activity_status, [NewResource], [Activity])
    golem.event_bus.resource_listen(note_activity_destroyed, [ResourceClosed], [Activity])

    async with golem:
        allocation = await golem.create_allocation(amount=1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        payment_manager = DefaultPaymentManager(golem, allocation)

        try:
            async for activity in Chain(
                demand.initial_proposals(),
                SimpleScorer(default_score_proposal, min_proposals=10),
                Map(default_negotiate),
                Map(default_create_agreement),
                Map(default_create_activity),
                Map(default_prepare_activity),
                ActivityPool(max_size=MAX_WORKERS),
                Zip(async_queue_aiter(tasks_queue)),
                Map(
                    lambda activity, task: task.execute(activity),
                    on_exception=close_agreement_repeat_task,
                ),
                Buffer(size=max(MAX_WORKERS, 2)),
            ):
                pass
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


def _get_summary_data(act_subset=None):
    total_results = len(results)
    total_batches = sum(data['batch_cnt'] for data in activity_data.values())
    batch_result_ratio = total_batches / total_results if total_results else 0

    selected_activity_data = {
        activity: data for activity, data in activity_data.items() if act_subset is None or activity in act_subset
    }

    total_glm = sum(data['glm'] for data in selected_activity_data.values())

    total_last_dn_batches = sum(data['last_dn_batch_cnt'] for data in selected_activity_data.values())
    total_last_dn_results = total_last_dn_batches / batch_result_ratio if batch_result_ratio else 0
    glm_batch_ratio = total_glm / total_last_dn_batches if total_last_dn_batches else 0
    glm_result_ratio = total_glm / total_last_dn_results if total_last_dn_results else 0

    agg_data = []
    for activity, data in selected_activity_data.items():
        activity_batches = data['batch_cnt']
        activity_last_dn_batches = data['last_dn_batch_cnt']
        activity_glm = data['glm']
        activity_status = data['status']

        activity_results = activity_batches / batch_result_ratio if batch_result_ratio else 0
        activity_last_dn_results = activity_last_dn_batches / batch_result_ratio if batch_result_ratio else 0

        activity_glm_result_ratio = round(activity_glm / activity_last_dn_results, 6) if activity_last_dn_results else 0

        agg_data.append([
            activity.id,
            round(activity_results, 2),
            round(activity_glm, 6),
            activity_glm_result_ratio,
            activity_batches,
            round(activity_glm / activity_last_dn_batches, 6) if activity_last_dn_batches else 0,
            "X" if activity_glm_result_ratio > MAX_GLM_PER_RESULT else "",
            activity_status,
        ])

    print(act_subset is None, agg_data[0])

    agg_data.append([
        'TOTAL',
        round(sum(row[1] for row in agg_data)),
        round(total_glm, 6),
        round(glm_result_ratio, 6),
        sum(row[4] for row in agg_data),
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
