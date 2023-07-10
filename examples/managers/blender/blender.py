import asyncio
import json
import logging.config
from datetime import timedelta
from pathlib import Path

from golem.managers.base import WorkContext
from golem.managers.proposal.plugins import MapScore
from golem.managers.proposal.pricings import LinearAverageCostPricing
from golem.managers.work.plugins import retry
from golem.payload import RepositoryVmPayload
from golem.utils.blender_api import run_on_golem
from golem.utils.logging import DEFAULT_LOGGING


from typing import List

from golem.managers.activity.pool import ActivityPoolManager
from golem.managers.agreement.single_use import SingleUseAgreementManager
from golem.managers.base import WorkResult
from golem.managers.negotiation import SequentialNegotiationManager
from golem.managers.negotiation.plugins import AddChosenPaymentPlatform
from golem.managers.payment.pay_all import PayAllPaymentManager
from golem.managers.proposal import ScoredAheadOfTimeProposalManager
from golem.managers.work.asynchronous import AsynchronousWorkManager
from golem.node import GolemNode

BLENDER_IMAGE_HASH = "9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae"
FRAME_CONFIG_TEMPLATE = json.loads(Path(__file__).with_name("frame_params.json").read_text())
FRAMES = list(range(0, 60, 3))


async def run_on_golem(
    task_list,
    payload,
    init_func,
    threads=6,
    budget=1.0,
    market_plugins=[
        AddChosenPaymentPlatform(),
    ],
    scoring_plugins=None,
    task_plugins=None,
):
    golem = GolemNode()

    payment_manager = PayAllPaymentManager(golem, budget=budget)
    negotiation_manager = SequentialNegotiationManager(
        golem,
        payment_manager.get_allocation,
        payload,
        plugins=market_plugins,
    )
    proposal_manager = ScoredAheadOfTimeProposalManager(
        golem, negotiation_manager.get_proposal, plugins=scoring_plugins
    )
    agreement_manager = SingleUseAgreementManager(golem, proposal_manager.get_proposal)
    activity_manager = ActivityPoolManager(
        golem, agreement_manager.get_agreement, size=threads, on_activity_start=init_func
    )
    work_manager = AsynchronousWorkManager(
        golem, activity_manager.do_work, plugins=task_plugins
    )

    async with golem, payment_manager, negotiation_manager, proposal_manager, activity_manager:
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
        threads=6,
        budget=1.0,
        task_plugins=[retry(tries=3)],
        scoring_plugins=[
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
