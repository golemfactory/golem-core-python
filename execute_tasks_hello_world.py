import asyncio
from golem_core import commands, execute_tasks, Payload
from golem_core.low import Activity

TASK_DATA = list(range(7))
BUDGET = 1
PAYLOAD = Payload.from_image_hash("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def execute_task(activity: Activity, in_data: int) -> str:
    batch = await activity.execute_commands(
        commands.Run(f"echo -n 'Executing task {in_data}'"),
    )
    await batch.wait(5)
    assert batch.events[0].stdout is not None
    return batch.events[0].stdout


async def main() -> None:
    async for result in execute_tasks(
        execute_task=execute_task,
        task_data=TASK_DATA,
        budget=BUDGET,
        payload=PAYLOAD,
    ):
        print("TASK RESULT", result)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    task = loop.create_task(main())
    loop.run_until_complete(task)
