import asyncio

from golem_api.high.execute_tasks import execute_tasks

from blender_mid import prepare_activity, execute_task, FRAMES

IMAGE_HASH = "9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae"
BUDGET = 1


async def main() -> None:
    async for result in execute_tasks(
        prepare_activity=prepare_activity,
        execute_task=execute_task,
        task_data=FRAMES,
        budget=BUDGET,
        vm_image_hash=IMAGE_HASH,
        max_workers=6,
    ):
        print("TASK RESULT", result)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    task = loop.create_task(main())
    loop.run_until_complete(task)
