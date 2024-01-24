import asyncio
from collections import defaultdict
from typing import (
    AsyncIterator,
    Callable,
    DefaultDict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypedDict,
    TypeVar,
    Union,
)

from prettytable import PrettyTable

from examples.task_api_draft.examples.yacat_no_business_logic import (
    PAYLOAD,
    main_task_source,
    results,
    tasks_queue,
)
from examples.task_api_draft.task_api.activity_pool import ActivityPool
from golem.event_bus import Event
from golem.node import GolemNode
from golem.pipeline import Buffer, Chain, DefaultPaymentHandler, Map, Sort, Zip
from golem.resources import (
    Activity,
    DebitNote,
    NewDebitNote,
    NewResource,
    PoolingBatch,
    Proposal,
    ResourceClosed,
    default_create_activity,
    default_create_agreement,
    default_negotiate,
    default_prepare_activity,
)
from golem.utils.logging import DefaultLogger

###########################
#   APP LOGIC CONFIG
MAX_GLM_PER_RESULT = 0.00001
NEW_PERIOD_SECONDS = 400
MIN_NEW_BATCHES = 10
MAX_WORKERS = 30
MAX_LINEAR_COEFFS = [0.001, 0.001, 0]


#################
#   "DATABASE"
class ActivityDataType(TypedDict):
    batch_cnt: int
    last_dn_batch_cnt: int
    glm: float
    status: str


activity_data: DefaultDict[Activity, ActivityDataType] = defaultdict(
    lambda: dict(batch_cnt=0, last_dn_batch_cnt=0, glm=0, status="")
)


#####################
#   EVENT CALLBACKS
async def count_batches(event: NewResource) -> None:
    activity = event.resource.parent
    activity_data[activity]["batch_cnt"] += 1


async def gather_debit_note_log(event: NewResource) -> None:
    debit_note: DebitNote = event.resource
    activity_id = (await debit_note.get_data()).activity_id
    if not any(activity.id == activity_id for activity in activity_data):
        #   This is a debit note for an unknown activity (e.g. from a previous run)
        return

    activity = debit_note.node.activity(activity_id)
    current_glm = activity_data[activity]["glm"]
    new_glm = max(current_glm, float(debit_note.data.total_amount_due))
    activity_data[activity]["glm"] = new_glm
    activity_data[activity]["last_dn_batch_cnt"] = activity_data[activity]["batch_cnt"]


async def note_activity_destroyed(event: ResourceClosed) -> None:
    activity: Activity = event.resource
    if activity not in activity_data:
        #   Destroyed activity from a previous run
        return

    current_status = activity_data[activity]["status"]
    if current_status in ("new", "ok"):
        activity_data[activity]["status"] = "Dead [unknown reason]"


async def update_new_activity_status(event: NewResource) -> None:
    activity: Activity = event.resource
    activity_data[activity]["status"] = "new"

    if not activity.has_parent:
        activity_data[activity]["status"] = "old run activity"

        #   This is an Activity from some other run
        #   (this will not happen in the future, session ID will prevent this)

        async def destroy() -> None:
            await activity.destroy()

        asyncio.create_task(destroy())

    async def set_ok_status() -> None:
        await asyncio.sleep(NEW_PERIOD_SECONDS)
        if activity_data[activity]["status"] == "new":
            if activity_data[activity]["batch_cnt"] >= MIN_NEW_BATCHES:
                activity_data[activity]["status"] = "ok"
            else:
                activity_data[activity]["status"] = "stopping"
                await activity.parent.close_all()
                activity_data[activity]["status"] = "Dead [weak worker]"

    asyncio.create_task(set_ok_status())


##########################
#   MAIN LOGIC
async def score_proposal(proposal: Proposal) -> Optional[float]:
    properties = proposal.data.properties
    if properties["golem.com.pricing.model"] != "linear":
        return None

    coeffs = properties["golem.com.pricing.model.linear.coeffs"]
    for val, max_val in zip(coeffs, MAX_LINEAR_COEFFS):
        if val > max_val:
            return None
    else:
        return 1 - (coeffs[0] + coeffs[1])


async def manage_activities() -> None:
    while True:
        await asyncio.sleep(5)

        ok_activities = {
            activity: data for activity, data in activity_data.items() if data["status"] == "ok"
        }
        if not ok_activities:
            continue

        summary_data = _get_summary_data(list(ok_activities))
        too_expensive = summary_data[-1][3] > MAX_GLM_PER_RESULT  # type: ignore
        if not too_expensive:
            continue

        print(
            f"TOO EXPENSIVE - target: {MAX_GLM_PER_RESULT}, current 'ok' activities:"
            f" {summary_data[-1][3]}"
        )

        most_expensive = max(
            ok_activities,
            key=lambda activity: ok_activities[activity]["glm"]
            / ok_activities[activity]["batch_cnt"],
        )
        print(f"Stopping {most_expensive} because it's most expensive")
        activity_data[most_expensive]["status"] = "Dead [too expensive]"
        await most_expensive.parent.close_all()


async def main() -> None:
    asyncio.create_task(main_task_source())
    asyncio.create_task(print_current_data())
    asyncio.create_task(manage_activities())

    golem = GolemNode()
    await golem.event_bus.on(Event, DefaultLogger().on_event)
    await golem.event_bus.on(
        NewResource, count_batches, lambda e: isinstance(e.resource, PoolingBatch)
    )
    await golem.event_bus.on(NewDebitNote, gather_debit_note_log)
    await golem.event_bus.on(
        NewResource, update_new_activity_status, lambda e: isinstance(e.resource, Activity)
    )
    await golem.event_bus.on(
        ResourceClosed, note_activity_destroyed, lambda e: isinstance(e.resource, Activity)
    )

    async with golem:
        allocation = await golem.create_allocation(amount=1)
        payment_handler = DefaultPaymentHandler(golem, allocation)

        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        try:
            async for activity in Chain(
                demand.initial_proposals(),
                Sort(score_proposal, min_elements=10),
                Map(default_negotiate),
                Map(default_create_agreement),
                Map(default_create_activity),
                Map(default_prepare_activity),
                ActivityPool(max_size=MAX_WORKERS),
                Zip(async_queue_aiter(tasks_queue)),  # type: ignore  # mypy, why?
                Map(
                    lambda activity, task: task.execute(activity),  # type: ignore
                    on_exception=close_agreement_repeat_task,
                ),
                Buffer(size=MAX_WORKERS * 2),
            ):
                pass
        except asyncio.CancelledError:
            await payment_handler.terminate_agreements()
            await payment_handler.wait_for_invoices()

    #   TODO: This removes the "destroyed but pending" messages, probably there's
    #         some even prettier solution available?
    [task.cancel() for task in asyncio.all_tasks()]


#############################################
#   NOT REALLY INTERESTING PARTS OF THE LOGIC
async def close_agreement_repeat_task(func: Callable, args: Tuple, e: Exception) -> None:
    activity, task = args
    tasks_queue.put_nowait(task)
    print("Task failed on", activity)
    activity_data[activity]["status"] = "Dead [task failed]"
    await activity.parent.close_all()


async def print_current_data() -> None:
    while True:
        await asyncio.sleep(15)
        _print_summary_table()


#############
#   UTILITIES
def round_float_str(x: float) -> str:
    if x == 0:
        return "0"
    if x < 0.000001:
        return "< 0.000001"
    else:
        return f"{round(x, 6):.6f}"


def _print_summary_table() -> None:
    agg_data = _get_summary_data()
    table = PrettyTable()
    table.field_names = [
        "ix",
        "activity_id",
        "results",
        "GLM",
        "GLM/result",
        "batches",
        "GLM/batch",
        "> " + round_float_str(MAX_GLM_PER_RESULT),
        "status",
    ]

    for row_ix, row in enumerate(agg_data):
        str_row = []
        if row_ix < len(agg_data) - 1:
            str_row.append(str(row_ix + 1))
        else:
            str_row.append("")
        for el_ix, el in enumerate(row):
            if el_ix in (2, 3, 5):
                str_row.append(round_float_str(el))  # type: ignore
            else:
                str_row.append(el)  # type: ignore
        table.add_row(str_row)
    print(table.get_string())


def _get_summary_data(
    act_subset: Optional[Iterable[Activity]] = None,
) -> List[List[Union[str, float]]]:
    total_results = len(results)
    total_batches = sum(data["batch_cnt"] for data in activity_data.values())
    batch_result_ratio = total_batches / total_results if total_results else 0

    selected_activity_data = {
        activity: data
        for activity, data in activity_data.items()
        if act_subset is None or activity in act_subset
    }

    total_glm = sum(data["glm"] for data in selected_activity_data.values())

    total_last_dn_batches = sum(
        data["last_dn_batch_cnt"] for data in selected_activity_data.values()
    )
    total_last_dn_results = total_last_dn_batches / batch_result_ratio if batch_result_ratio else 0
    glm_batch_ratio = total_glm / total_last_dn_batches if total_last_dn_batches else 0
    glm_result_ratio = total_glm / total_last_dn_results if total_last_dn_results else 0

    agg_data: List[List[Union[str, float]]] = []
    for activity, data in selected_activity_data.items():
        activity_batches = data["batch_cnt"]
        activity_last_dn_batches = data["last_dn_batch_cnt"]
        activity_glm = data["glm"]
        activity_status = data["status"]

        activity_results = activity_batches / batch_result_ratio if batch_result_ratio else 0
        activity_last_dn_results = (
            activity_last_dn_batches / batch_result_ratio if batch_result_ratio else 0
        )

        activity_glm_result_ratio = (
            round(activity_glm / activity_last_dn_results, 6) if activity_last_dn_results else 0
        )

        agg_data.append(
            [
                activity.id,
                round(activity_results, 2),
                round(activity_glm, 6),
                activity_glm_result_ratio,
                activity_batches,
                round(activity_glm / activity_last_dn_batches, 6)
                if activity_last_dn_batches
                else 0,
                "X" if activity_glm_result_ratio > MAX_GLM_PER_RESULT else "",
                activity_status,
            ]
        )

    agg_data.append(
        [
            "TOTAL",
            round(sum(row[1] for row in agg_data)),  # type: ignore
            round(total_glm, 6),
            round(glm_result_ratio, 6),
            sum(row[4] for row in agg_data),  # type: ignore
            round(glm_batch_ratio, 6),
            "X" if glm_result_ratio > MAX_GLM_PER_RESULT else "",
            "",
        ]
    )
    return agg_data


AnyType = TypeVar("AnyType")


async def async_queue_aiter(src_queue: "asyncio.Queue[AnyType]") -> AsyncIterator[AnyType]:
    while True:
        yield await src_queue.get()


if __name__ == "__main__":
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
