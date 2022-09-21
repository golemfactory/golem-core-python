import asyncio
from datetime import timedelta
import json
from pathlib import Path
from random import random

from golem_api import commands, GolemNode, Payload
from golem_api.low import Activity, Proposal

from golem_api.mid import (
    Chain, SimpleScorer, DefaultNegotiator, AgreementCreator, ActivityCreator, Map, ExecuteTasks, ActivityPool
)
from golem_api.default_logger import DefaultLogger
from golem_api.default_payment_manager import DefaultPaymentManager


FRAME_CONFIG_TEMPLATE = json.loads(Path("frame_params.json").read_text())
FRAMES = list(range(0, 60, 10))
PAYLOAD = Payload.from_image_hash("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")


async def score_proposal(proposal: Proposal) -> float:
    return random()


async def prepare_activity(activity: Activity) -> Activity:
    print(f"Prepare activity {activity}")
    batch = await activity.execute_commands(
        commands.Deploy(),
        commands.Start(),
        commands.SendFile("cubes.blend", "/golem/resource/scene.blend")
    )
    await batch.wait(timeout=10)
    assert batch.events[-1].result == 'Ok'
    return activity


async def execute_task(activity: Activity, frame_ix: int) -> str:
    print(f"Execute task {frame_ix} on activity {activity}")
    frame_config = FRAME_CONFIG_TEMPLATE.copy()
    frame_config["frames"] = [frame_ix]
    fname = f"out{frame_ix:04d}.png"
    batch = await activity.execute_commands(
        commands.Run("/bin/sh", ["-c", f"echo '{json.dumps(frame_config)}' > /golem/work/params.json"]),
        commands.Run("/golem/entrypoints/run-blender.sh", []),
        commands.DownloadFile(f"/golem/output/{fname}", fname)
    )

    await batch.wait(timeout=20)
    assert batch.events[-1].result == 'Ok'

    return fname


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1)

        payment_manager = DefaultPaymentManager(golem, allocation)

        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(score_proposal, min_proposals=10, max_wait=timedelta(seconds=0.1)),
            DefaultNegotiator(),
            AgreementCreator(),
            ActivityCreator(),
            Map(prepare_activity, True),
            ActivityPool(max_size=5),
            ExecuteTasks(execute_task, FRAMES),
        )

        out_files = []
        async for out_file in chain:
            out_files.append(out_file)
            print(f"Frame {len(out_files)}/{len(FRAMES)} {out_file}")

        print("DONE")
        assert len(out_files) == len(FRAMES)

        await payment_manager.terminate_agreements()
        await payment_manager.wait_for_invoices()


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
