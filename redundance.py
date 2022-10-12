import asyncio

from golem_api import commands, execute_tasks, Payload
from golem_api.low import Activity

PAYLOAD = Payload.from_image_hash("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def execute_task(activity: Activity, task_data: int) -> str:
    batch = await activity.execute_commands(
        commands.Run(f"echo -n 'DATA {task_data}'"),
    )
    await batch.wait(timeout=5)
    return batch.events[-1].stdout


async def main() -> None:
    async for result in execute_tasks(
        budget=1,
        execute_task=execute_task,
        task_data=list(range(10)),
        payload=PAYLOAD,
        max_workers=5,
        redundance=0.6,
    ):
        print(f"GOT RESULT {result}")

    print("DONE")

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
