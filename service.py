import asyncio
import random
import string
from uuid import uuid4
from urllib.parse import urlparse

from yapapi.payload import vm

from golem_api import GolemNode, Payload, commands
from golem_api.mid import (
    Buffer, Chain, Limit, Map,
    default_negotiate, default_create_agreement, default_create_activity
)
from golem_api.default_logger import DefaultLogger

PAYLOAD = Payload.from_image_hash(
    "1e06505997e8bd1b9e1a00bd10d255fc6a390905e4d6840a22a79902",
    capabilities=[vm.VM_CAPS_VPN],
)

def create_ssh_connection(network):
    async def _create_ssh_connection(activity):
        #   1.  Create node
        provider_id = activity.parent.parent.data.issuer_id
        node = await network.create_node(provider_id)

        #   2.  Run commands
        deploy_args = node.deploy_args()
        password = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(8))

        batch = await activity.execute_commands(
            commands.Deploy(deploy_args),
            commands.Start(),
            commands.Run("syslogd"),
            commands.Run("ssh-keygen -A"),
            commands.Run(f'echo -e "{password}\n{password}" | passwd'),
            commands.Run("/usr/sbin/sshd"),
        )
        await batch.wait(20)

        #   3.  Create connection uri
        url = network.node._api_config.net_url
        net_api_ws = urlparse(url)._replace(scheme="ws").geturl()
        connection_uri = f"{net_api_ws}/net/{network.id}/tcp/{node.data.ip}/22"

        return connection_uri, password
    return _create_ssh_connection


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        network = await golem.create_network("192.168.0.1/24")
        await golem.add_to_network(network)

        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        connections = []
        async for uri, password in Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(create_ssh_connection(network)),
            Limit(2),
            Buffer(2),
        ):
            connections.append((uri, password))

        await network.refresh_nodes()

        for uri, password in connections:
            print(
                "Connect with:\n"
                f"  ssh -o ProxyCommand='websocat asyncstdio: {uri} --binary "
                f"-H=Authorization:\"Bearer {golem._api_config.app_key}\"' root@{uuid4().hex} "
                f"\n  password: {password}"
            )

        await asyncio.Future()


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
