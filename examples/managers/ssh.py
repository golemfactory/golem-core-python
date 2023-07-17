import asyncio
import logging.config
import random
import string
from uuid import uuid4

from golem.managers.activity.single_use import SingleUseActivityManager
from golem.managers.agreement.scored_aot import ScoredAheadOfTimeAgreementManager
from golem.managers.base import WorkContext, WorkResult
from golem.managers.demand.auto import AutoDemandManager
from golem.managers.negotiation import SequentialNegotiationManager
from golem.managers.network.single import SingleNetworkManager
from golem.managers.payment.pay_all import PayAllPaymentManager
from golem.managers.work.sequential import SequentialWorkManager
from golem.node import GolemNode
from golem.payload import RepositoryVmPayload
from golem.utils.logging import DEFAULT_LOGGING


def on_activity_start(get_network_deploy_args):
    async def _on_activity_start(context: WorkContext):
        deploy_args = {
            "net": [await get_network_deploy_args(context._activity.parent.parent.data.issuer_id)]
        }
        batch = await context.create_batch()
        batch.deploy(deploy_args)
        batch.start()
        await batch()

    return _on_activity_start


def work(app_key, get_provider_uri):
    async def _work(context: WorkContext) -> str:
        password = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        batch = await context.create_batch()
        batch.run("syslogd")
        batch.run("ssh-keygen -A")
        batch.run(f'echo -e "{password}\n{password}" | passwd')
        batch.run("/usr/sbin/sshd")
        batch_result = await batch()
        result = ""
        for event in batch_result:
            result += f"{event.stdout}"

        print(
            "Connect with:\n"
            "  ssh -o ProxyCommand='websocat asyncstdio: "
            f"{await get_provider_uri(context._activity.parent.parent.data.issuer_id, 'ws')}"
            f" --binary "
            f'-H=Authorization:"Bearer {app_key}"\' root@{uuid4().hex} '
        )
        print(f"PASSWORD: {password}")

        for _ in range(3):
            await asyncio.sleep(1)
        return result

    return _work


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
    demand_manager = AutoDemandManager(
        golem,
        payment_manager.get_allocation,
        payload,
    )
    negotiation_manager = SequentialNegotiationManager(golem, demand_manager.get_initial_proposal)
    agreement_manager = ScoredAheadOfTimeAgreementManager(
        golem, negotiation_manager.get_draft_proposal
    )
    activity_manager = SingleUseActivityManager(
        golem,
        agreement_manager.get_agreement,
        on_activity_start=on_activity_start(network_manager.get_deploy_args),
    )
    work_manager = SequentialWorkManager(golem, activity_manager.do_work)
    # TODO use different managers so it allows to finish work func without destroying activity
    async with golem, network_manager, payment_manager, demand_manager, negotiation_manager, agreement_manager:  # noqa: E501 line too long
        result: WorkResult = await work_manager.do_work(
            work(golem._api_config.app_key, network_manager.get_provider_uri)
        )
        print(f"\nWORK MANAGER RESULTS:{result.result}\n")


if __name__ == "__main__":
    asyncio.run(main())
