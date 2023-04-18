import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Optional, Tuple

from golem_core.core.golem_node import GolemNode
from golem_core.utils.logging import DefaultLogger
from golem_core.core.payment_api import DefaultPaymentManager
from golem_core.core.activity_api import commands, Activity
from golem_core.pieline import (
    Buffer,
    Chain,
    Limit,
    Map,
)
from golem_core.core.market_api import (
    default_negotiate,
    default_create_agreement,
    default_create_activity,
    RepositoryVmPayload, Proposal,
)

FRAME_CONFIG_TEMPLATE = json.loads(Path("frame_params.json").read_text())
PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

# scores will contain time of profiling execution
scores: Dict[str, Optional[timedelta]] = {}


async def delay(delay: timedelta, func: Callable) -> Any:
    await asyncio.sleep(delay.total_seconds())
    return func()


async def filter_rated_providers(offer_stream: AsyncIterator[Proposal]) -> AsyncIterator[Proposal]:
    async for offer in offer_stream:
        provider_id = offer.data.issuer_id
        if provider_id is None:
            continue
        if provider_id not in scores:
            scores[provider_id] = None
            yield offer


async def prepare_activity(activity: Activity) -> Activity:
    print(f"Prepare {activity}")
    batch = await activity.execute_commands(
        commands.Deploy(),
        commands.Start(),
        commands.SendFile("cubes.blend", "/golem/resource/scene.blend"),
    )
    await batch.wait(timeout=120)
    return activity


async def rate_provider(activity: Activity) -> str:
    provider_id = activity.parent.parent.data.issuer_id
    assert provider_id is not None
    print(f"Rating {provider_id}")
    frame_config = FRAME_CONFIG_TEMPLATE.copy()
    fname = f"out{0:04d}.png"  # format used by `run-blender.sh` included in `PAYLOAD`
    output_file = f"{provider_id}-{fname}"

    start_time = datetime.utcnow()
    batch = await activity.execute_commands(
        commands.Run(f"echo '{json.dumps(frame_config)}' > /golem/work/params.json"),
        commands.Run(["/golem/entrypoints/run-blender.sh"]),
        commands.DownloadFile(f"/golem/output/{fname}", output_file),
    )
    await batch.wait(timeout=20)

    end_time = datetime.utcnow()
    scores[provider_id] = end_time - start_time

    return output_file


async def on_exception(func: Callable, args: Tuple, e: Exception) -> None:
    activity = args[0]
    print(f"Activity {activity} failed because of:\n{e}")
    await activity.parent.close_all()


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1.0)
        payment_manager = DefaultPaymentManager(golem, allocation)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        # `set_no_more_children` has to be called so `initial_proposals` will eventually stop yielding
        asyncio.create_task(delay(timedelta(seconds=5), demand.set_no_more_children))

        chain = Chain(
            demand.initial_proposals(),
            filter_rated_providers,
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(prepare_activity),
            Map(rate_provider, on_exception=on_exception),
            Limit(10),
            Buffer(5),
        )

        async for result in chain:
            print(f"Finished rating provider with {result}.")
            print("We have following ratings:")
            print(f"{[(s, scores[s]) for s in scores if scores[s] is not None]}")

        print(
            f"TASK DONE"
        )
        await payment_manager.terminate_agreements()
        await payment_manager.wait_for_invoices()


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
