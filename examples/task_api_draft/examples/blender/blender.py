import asyncio
import json
from pathlib import Path

from examples.task_api_draft.task_api.execute_tasks import execute_tasks
from golem_core.core.activity_api import Activity, commands
from golem_core.core.market_api import RepositoryVmPayload

FRAME_CONFIG_TEMPLATE = json.loads(Path("frame_params.json").read_text())
FRAMES = list(range(0, 60, 10))
PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def prepare_activity(activity: Activity) -> Activity:
    print(f"Prepare {activity}")
    batch = await activity.execute_commands(
        commands.Deploy(),
        commands.Start(),
        commands.SendFile("cubes.blend", "/golem/resource/scene.blend")
    )
    await batch.wait(timeout=60)
    return activity


async def execute_task(activity: Activity, frame_ix: int) -> str:
    print(f"Rendering frame {frame_ix} on {activity}")
    frame_config = FRAME_CONFIG_TEMPLATE.copy()
    frame_config["frames"] = [frame_ix]
    fname = f"out{frame_ix:04d}.png"

    batch = await activity.execute_commands(
        commands.Run(f"echo '{json.dumps(frame_config)}' > /golem/work/params.json"),
        commands.Run(["/golem/entrypoints/run-blender.sh"]),
        commands.DownloadFile(f"/golem/output/{fname}", fname)
    )
    await batch.wait(timeout=20)
    return fname


async def main() -> None:
    out_files = []
    async for out_fname in execute_tasks(
        budget=1,
        prepare_activity=prepare_activity,
        execute_task=execute_task,
        task_data=FRAMES,
        payload=PAYLOAD,
        max_workers=5,
    ):
        out_files.append(out_fname)
        print(f"Frame {len(out_files)}/{len(FRAMES)} {out_fname}")

    print("DONE")
    assert len(out_files) == len(FRAMES)

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
