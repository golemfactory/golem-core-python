import asyncio

from golem_api import execute_tasks

from blender_mid import prepare_activity, execute_task, FRAMES, PAYLOAD


async def main() -> None:
    async for out_fname in execute_tasks(
        budget=1,
        prepare_activity=prepare_activity,
        execute_task=execute_task,
        task_data=FRAMES,
        payload=PAYLOAD,
        max_workers=5,
    ):
        print(f"File ready: {out_fname}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    task = loop.create_task(main())
    loop.run_until_complete(task)
