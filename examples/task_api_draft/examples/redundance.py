import asyncio
import random

from examples.task_api_draft.task_api.execute_tasks import execute_tasks
from golem_core.core.activity_api import Activity, commands
from golem_core.core.market_api import RepositoryVmPayload

PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def execute_task(activity: Activity, task_data: int) -> str:
    batch = await activity.execute_commands(
        commands.Run(f"echo -n '{task_data}'"),
    )
    await batch.wait(timeout=5)

    if random.random() < 0.9:
        result = batch.events[-1].stdout
        assert result is not None  # mainnet providers sometimes return None
    else:
        result = "BAD_RESULT"

    return result


async def main() -> None:
    async for result in execute_tasks(
        budget=1,
        execute_task=execute_task,
        task_data=list(range(10)),
        payload=PAYLOAD,
        max_workers=3,
        redundance=(3, 0.7),
    ):
        print(f"GOT RESULT {result}")

    print("DONE")


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
