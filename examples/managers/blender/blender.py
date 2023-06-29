import asyncio
import json
import logging.config
from pathlib import Path
from typing import List

from golem.managers.activity.pool import ActivityPoolManager
from golem.managers.agreement.single_use import SingleUseAgreementManager
from golem.managers.base import WorkContext, WorkResult
from golem.managers.negotiation import SequentialNegotiationManager
from golem.managers.negotiation.plugins import AddChosenPaymentPlatform
from golem.managers.payment.pay_all import PayAllPaymentManager
from golem.managers.proposal import StackProposalManager
from golem.managers.work.asynchronous import AsynchronousWorkManager
from golem.managers.work.plugins import retry
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING

FRAME_CONFIG_TEMPLATE = json.loads(Path(__file__).with_name("frame_params.json").read_text())
FRAMES = list(range(0, 60, 10))


async def load_blend_file(context: WorkContext):
    batch = await context.create_batch()
    batch.deploy()
    batch.start()
    batch.send_file(str(Path(__file__).with_name("cubes.blend")), "/golem/resource/scene.blend")
    await batch()


def blender_frame_work(frame_ix: int):
    async def _blender_frame_work(context: WorkContext) -> str:
        frame_config = FRAME_CONFIG_TEMPLATE.copy()
        frame_config["frames"] = [frame_ix]
        fname = f"out{frame_ix:04d}.png"
        fname_path = str(Path(__file__).parent / fname)

        print(f"BLENDER: Running {fname_path}")

        batch = await context.create_batch()
        batch.run(f"echo '{json.dumps(frame_config)}' > /golem/work/params.json")
        batch.run("/golem/entrypoints/run-blender.sh")
        batch.download_file(f"/golem/output/{fname}", fname_path)
        await batch()
        return fname_path

    return _blender_frame_work


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

    work_list = [blender_frame_work(frame_ix) for frame_ix in FRAMES]

    golem = GolemNode()

    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    negotiation_manager = SequentialNegotiationManager(
        golem,
        payment_manager.get_allocation,
        payload,
        plugins=[
            AddChosenPaymentPlatform(),
        ],
    )
    proposal_manager = StackProposalManager(golem, negotiation_manager.get_proposal)
    agreement_manager = SingleUseAgreementManager(golem, proposal_manager.get_proposal)
    activity_manager = ActivityPoolManager(
        golem, agreement_manager.get_agreement, size=3, on_activity_start=load_blend_file
    )
    work_manager = AsynchronousWorkManager(
        golem, activity_manager.do_work, plugins=[retry(tries=3)]
    )

    async with golem:
        async with payment_manager, negotiation_manager, proposal_manager, activity_manager:
            results: List[WorkResult] = await work_manager.do_work_list(work_list)
            print(f"\nWORK MANAGER RESULTS:{[result.result for result in results]}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
