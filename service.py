import asyncio
import random
import string
from uuid import uuid4
from urllib.parse import urlparse

from yapapi.payload import vm

from golem_api import GolemNode, Payload, commands
from golem_api.mid import (
    Chain, Map,
    default_negotiate, default_create_agreement, default_create_activity
)
from golem_api.default_logger import DefaultLogger

PAYLOAD = Payload.from_image_hash(
    "1e06505997e8bd1b9e1a00bd10d255fc6a390905e4d6840a22a79902",
    capabilities=[vm.VM_CAPS_VPN],
)


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        network = await golem.create_network("192.168.0.1/24")
        print(network)
        await golem.add_to_network(network)

        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        activity_chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
        )
        awaitable_1 = await activity_chain.__anext__()
        activity = await awaitable_1
        # awaitable_2 = await activity_chain.__anext__()
        # activity_1, activity_2 = await asyncio.gather(awaitable_1, awaitable_2)

        provider_id = activity.parent.parent.data.issuer_id
        node = await network.create_node(provider_id)
        print(node)

        deploy_args = {
            "net": [
                {
                    "id": network.id,
                    "ip": "192.168.0.0",
                    "mask": network.data.mask,
                    "nodeIp": node.data.ip,
                    "nodes": {node.data.ip: node.id for node in network.nodes},
                }
            ]
        }

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

        url = golem._api_config.net_url
        net_api_ws = urlparse(url)._replace(scheme="ws").geturl()
        connection_uri = f"{net_api_ws}/net/{network.id}/tcp/{node.data.ip}/22"

        print(
            "Connect with:\n"
            f"  ssh -o ProxyCommand='websocat asyncstdio: {connection_uri} --binary "
            f"-H=Authorization:\"Bearer {golem._api_config.app_key}\"' root@{uuid4().hex} "
            f"\n  password: {password}"
        )

        await asyncio.sleep(100)


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
