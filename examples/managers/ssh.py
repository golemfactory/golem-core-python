import asyncio
import logging.config
import random
import string
from uuid import uuid4

from golem.managers import (
    DefaultAgreementManager,
    DefaultProposalManager,
    NegotiatingPlugin,
    PayAllPaymentManager,
    PaymentPlatformNegotiator,
    RefreshingDemandManager,
    SequentialWorkManager,
    SingleNetworkManager,
    SingleUseActivityManager,
    WorkContext,
)
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING


class SshHandler:
    def __init__(self, app_key: str, network_manager: SingleNetworkManager) -> None:
        self._app_key = app_key
        self._network_manager = network_manager
        self.started = False

    async def on_activity_start(self, context: WorkContext):
        deploy_args = {
            "net": [
                await self._network_manager.get_deploy_args(
                    context._activity.parent.parent.data.issuer_id
                )
            ]
        }
        batch = await context.create_batch()
        batch.deploy(deploy_args)
        batch.start()
        await batch()

    async def work(self, context: WorkContext) -> None:
        password = await self._run_ssh_server(context)
        provider_id = context._activity.parent.parent.data.issuer_id
        print(
            "Connect with:\n"
            "  ssh -o ProxyCommand='websocat asyncstdio: "
            f"{await self._network_manager.get_provider_uri(provider_id, 'ws')}"
            f" --binary "
            f'-H=Authorization:"Bearer {self._app_key}"\' root@{uuid4().hex} '
        )
        print(f"PASSWORD: {password}")
        self.started = True
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            ...

    async def _run_ssh_server(self, context: WorkContext) -> str:
        password = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        batch = await context.create_batch()
        batch.run("syslogd")
        batch.run("ssh-keygen -A")
        batch.run(f'echo -e "{password}\n{password}" | passwd')
        batch.run("/usr/sbin/sshd")
        await batch()
        return password


async def main():
    logging.config.dictConfig(DEFAULT_LOGGING)
    payload = RepositoryVmPayload(
        "1e06505997e8bd1b9e1a00bd10d255fc6a390905e4d6840a22a79902",
        capabilities=["vpn"],
    )
    network_ip = "192.168.0.1/24"

    golem = GolemNode()

    network_manager = SingleNetworkManager(golem, network_ip)
    payment_manager = PayAllPaymentManager(golem, budget=1.0)
    demand_manager = RefreshingDemandManager(
        golem,
        payment_manager.get_allocation,
        [payload],
    )
    proposal_manager = DefaultProposalManager(
        golem,
        demand_manager.get_initial_proposal,
        plugins=[
            NegotiatingPlugin(proposal_negotiators=[PaymentPlatformNegotiator()]),
        ],
    )
    agreement_manager = DefaultAgreementManager(
        golem,
        proposal_manager.get_draft_proposal,
    )

    ssh_handler = SshHandler(golem._api_config.app_key, network_manager=network_manager)

    activity_manager = SingleUseActivityManager(
        golem,
        agreement_manager.get_agreement,
        on_activity_start=ssh_handler.on_activity_start,
    )
    work_manager = SequentialWorkManager(golem, activity_manager.get_activity)
    async with golem, network_manager, payment_manager, demand_manager, proposal_manager, agreement_manager:  # noqa: E501 line too long
        task = asyncio.create_task(work_manager.do_work(ssh_handler.work))
        while not ssh_handler.started:
            await asyncio.sleep(0.1)
        _, pending = await asyncio.wait((task,), timeout=20)
        [p.cancel() for p in pending]


if __name__ == "__main__":
    asyncio.run(main())
