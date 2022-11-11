import asyncio

from yapapi.payload import vm

from golem_api import GolemNode, Payload
from golem_api.mid import (
    Chain, Map,
    default_negotiate, default_create_agreement, default_create_activity, default_prepare_activity
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
        return

        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        activity_chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(default_prepare_activity),
        )
        awaitable_1 = await activity_chain.__anext__()
        awaitable_2 = await activity_chain.__anext__()
        activity_1, activity_2 = await asyncio.gather(awaitable_1, awaitable_2)

        print(activity_1, activity_2)


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
