import asyncio
import json
import logging.config
from datetime import timedelta
from pathlib import Path
from typing import List

from golem.managers import (
    AddChosenPaymentPlatform,
    ConcurrentWorkManager,
    DefaultAgreementManager,
    DefaultProposalManager,
    LinearAverageCostPricing,
    MapScore,
    NegotiatingPlugin,
    PayAllPaymentManager,
    PoolActivityManager,
    RefreshingDemandManager,
    ScoringBuffer,
    WorkContext,
    WorkResult,
    retry,
)
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING

BLENDER_IMAGE_HASH = "9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae"
FRAME_CONFIG_TEMPLATE = json.loads(Path(__file__).with_name("frame_params.json").read_text())
FRAMES = list(range(0, 60, 8))


async def run_on_golem(
    task_list,
    payload,
    init_func,
    threads=6,
    budget=1.0,
    negotiators=None,
    scorers=None,
    task_plugins=None,
):
    if negotiators is None:
        negotiators = [
            AddChosenPaymentPlatform(),
        ]

    golem = GolemNode()

    payment_manager = PayAllPaymentManager(golem, budget=budget)
    demand_manager = RefreshingDemandManager(
        golem,
        payment_manager.get_allocation,
        payload,
    )
    proposal_manager = DefaultProposalManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            NegotiatingPlugin(proposal_negotiators=negotiators),
            ScoringBuffer(
                min_size=3, max_size=5, fill_concurrency_size=3, proposal_scorers=scorers
            ),
        ],
    )
    agreement_manager = DefaultAgreementManager(
        golem,
        proposal_manager.get_draft_proposal,
    )
    activity_manager = PoolActivityManager(
        golem, agreement_manager.get_agreement, pool_size=threads, on_activity_start=init_func
    )
    work_manager = ConcurrentWorkManager(
        golem, activity_manager.get_activity, size=threads, plugins=task_plugins
    )

    async with golem, payment_manager, demand_manager, proposal_manager, agreement_manager, activity_manager:  # noqa: E501 line too long
        results: List[WorkResult] = await work_manager.do_work_list(task_list)
    return results


async def load_blend_file(context: WorkContext):
    batch = await context.create_batch()
    batch.deploy()
    batch.start()
    batch.send_file(str(Path(__file__).with_name("cubes.blend")), "/golem/resource/scene.blend")
    await batch()


def render_blender_frame(frame_ix: int):
    async def _render_blender_frame(context: WorkContext) -> str:
        frame_config = FRAME_CONFIG_TEMPLATE.copy()
        frame_config["frames"] = [frame_ix]
        fname = f"out{frame_ix:04d}.png"
        fname_path = str(Path(__file__).parent / "frames" / fname)

        print(f"BLENDER: Generating frame {fname_path}")

        batch = await context.create_batch()
        batch.run(f"echo '{json.dumps(frame_config)}' > /golem/work/params.json")
        batch.run("/golem/entrypoints/run-blender.sh")
        batch.download_file(f"/golem/output/{fname}", fname_path)
        await batch()

        print(f"BLENDER: Frame {fname_path} done")

        return fname_path

    return _render_blender_frame


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload(BLENDER_IMAGE_HASH)

    task_list = [render_blender_frame(frame_ix) for frame_ix in FRAMES]

    results = await run_on_golem(
        payload=payload,
        task_list=task_list,
        init_func=load_blend_file,
        threads=4,
        budget=1.0,
        task_plugins=[retry(tries=3)],
        scorers=[
            MapScore(
                LinearAverageCostPricing(
                    average_cpu_load=0.2, average_duration=timedelta(seconds=5)
                ),
                normalize=True,
                normalize_flip=True,
            ),
        ],
    )

    print(f"\nBLENDER: all frames:{[result.result for result in results]}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
