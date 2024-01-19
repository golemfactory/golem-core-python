import asyncio
import logging.config
from datetime import datetime, timedelta

from golem.managers import (
    Buffer,
    DefaultAgreementManager,
    DefaultProposalManager,
    MidAgreementPaymentsNegotiator,
    NegotiatingPlugin,
    PayAllPaymentManager,
    PaymentPlatformNegotiator,
    RefreshingDemandManager,
    SequentialWorkManager,
    SingleUseActivityManager,
    WorkContext,
    WorkResult,
)
from golem.node import GolemNode
from golem.payload import PaymentInfo, RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING

WORK_RUN_TIME = timedelta(minutes=60)


async def print_yagna_payment_status(yagna_path="yagna", network="goerli"):
    process = await asyncio.create_subprocess_exec(
        yagna_path,
        "payment",
        "status",
        "--network",
        network,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(
            f"Exited with code `{process.returncode!r}`!\nstdout:\n{stdout!r}\nstderr:\n{stderr!r}"
        )

    print(stdout.decode(), flush=True)


async def idle_work(context: WorkContext) -> str:
    work_start_time = datetime.utcnow()
    result = ""
    while datetime.utcnow() - work_start_time <= WORK_RUN_TIME:
        r = await context.run("echo 'hello golem'")
        await r.wait()
        for event in r.events:
            result += event.stdout

        await asyncio.sleep(60)
        await print_yagna_payment_status()

    return result


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    debit_notes_interval = timedelta(minutes=3)
    payment_timeout = timedelta(minutes=30)
    payloads = [
        # golem/alpine:3.18.2
        RepositoryVmPayload("1a0f2d0b1512018445a028c8f46151969ef8ddaaf3435ae118d3071d"),
        PaymentInfo(
            debit_notes_accept_timeout=180,
            debit_notes_interval=int(debit_notes_interval.total_seconds()),
            payment_timeout=int(payment_timeout.total_seconds()),
        ),
    ]
    await print_yagna_payment_status()

    golem = GolemNode()

    payment_manager = PayAllPaymentManager(golem, budget=10.0)
    demand_manager = RefreshingDemandManager(golem, payment_manager.get_allocation, payloads)
    proposal_manager = DefaultProposalManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            NegotiatingPlugin(
                proposal_negotiators=[
                    PaymentPlatformNegotiator(),
                    MidAgreementPaymentsNegotiator(
                        optimal_debit_note_interval=debit_notes_interval,
                        optimal_payment_timeout=payment_timeout,
                    ),
                ]
            ),
            Buffer(
                min_size=1,
                max_size=4,
                fill_concurrency_size=2,
            ),
        ],
    )
    agreement_manager = DefaultAgreementManager(golem, proposal_manager.get_draft_proposal)
    activity_manager = SingleUseActivityManager(golem, agreement_manager.get_agreement)
    work_manager = SequentialWorkManager(golem, activity_manager.get_activity)

    async with golem:
        async with payment_manager, demand_manager, proposal_manager, agreement_manager:
            work_result: WorkResult = await work_manager.do_work(idle_work)
            print(f"\nWORK MANAGER RESULT:{work_result.result}\n", flush=True)

    await print_yagna_payment_status()


if __name__ == "__main__":
    asyncio.run(main())
