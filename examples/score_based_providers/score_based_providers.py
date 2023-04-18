import asyncio
from datetime import timedelta
from typing import Callable, Dict, Optional, Tuple

from golem_core.core.activity_api import Activity, commands
from golem_core.core.golem_node import GolemNode
from golem_core.core.market_api import (
    RepositoryVmPayload,
    Proposal,
    SimpleScorer,
    default_negotiate,
    default_create_agreement, default_create_activity,
)
from golem_core.core.payment_api import DefaultPaymentManager
from golem_core.pipeline import (
    Buffer,
    Chain,
    Map,
    Limit,
)
from golem_core.utils.logging import DefaultLogger

PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

SELECT_MIN_PROPOSALS = 2
SELECT_MIN_TIME = timedelta(seconds=10)
SELECT_MAX_TIME = timedelta(minutes=1)


PROVIDER_SCORES: Dict[str, float] = {
    "0xa569c2fc7757a0235bb02de7897a715536ebc698": 0.9,  # golem2004.h
    "0x52b10b8d1e7dc4891a435b932f2b6992c899d18a": 0.9,  # golem2005.h
    "0x595c0c352dd0de2ec805ac39cff70fcddbecab12": 0.8,  # imapp1019.h
    "0x41a881d180f9b83a93bf54ffa487a609dd7e3ef1": 0.8,  # imapp2020.h
    "0x7a66c99526899f9e01c275e0cefc18e011238497": 0.8,  # imapp2025.h
    "0x7ea10e5b7f76f973c753dc63928f1365f48a63c5": 0.8,  # imapp2030.h
    "0x87af9bf7c7e8f37ef091b86d245c119fe5acabba": 0.7,  # 10hx4r2.h
    "0x85f85b8c071a5b2fea0eee7e0c824ace51ba469f": 0.7,  # 10jx4r2.h
    "0x74835ba53e9bf894ab06d4ec9cc557d5fa8ecdbb": 0.7,  # 1nxt4s2.h
    "0xba09bd90bac4b6cfe30da4178f68c495a59fcbe1": 0.7,  # 4gdpwl2.h
    "0x992d2099e3e0d48ebe7e5686a28f9117f3812a67": 0.7,  # 65h5jn2.h
    "0xe61444655190f8bee2401f6e13d8a41ae00d2c70": 0.7,  # Fermi I
    "0xfd25f222f5debd48e7530f104a0ab2d2db7f9886": 0.7,  # azathoth-rnd.h
    "0xccb9504c3a8fdb3a6984eb514112676829aa4202": 0.7,  # bristlecone.h
    "0x114e4ec2b33cb86a4e866ee95efcf12bde9dd5c7": 0.7,  # czc8358cgc.h
    "0xd0319089e4b6c41ff0950c214c951bdf0516893b": 0.7,  # etam.h
    "0xa5d358145d361910657db4ff148c043c4b271c7d": 0.7,  # fbwk2t2.h
    "0xc5bedb68059a3b38e48ff61fb124c370f7487b98": 0.7,  # fractal_01.h
    "0xc715f4833db14d20c13f82f0559eeca56ffe3451": 0.7,  # fractal_02.h
    # "0xfd63f54df8dda960f5ee69058875fe979c7676da": 0.7,  # g505sp2.h
    # "0xed827a418ddd23ead600ce8c4d1fed662a330fdf": 0.7,  # jiuzhang.h
    # "0x6b3b050959aacc3666932852ee34eb290ce15111": 0.7,  # m1
    # "0x18d3a6c5838c652be1c7b2fa92ac0d7353f5e8fe": 0.7,  # michal.h
    # "0x7d2e5c5f845de0475585efaff754bc9c96b5fbf4": 0.7,  # q53.h
    # "0xb8337a8a6036125b33eebe64bd1f2cd224a1555b": 0.7,  # sd-3060
    # "0x2c7b400ca93bf23bc88d532a0f4ba5445e5bf520": 0.7,  # sd-3090
    # "0x6e53d47fa38d9e768fabc0b6ad42910148ffbc4b": 0.7,  # sharkoon_378.h
    # "0xc327483fd029b19d0fa7a9a378a8cdbf0ae5a97f": 0.7,  # sharkoon_379.h
    # "0xd385526f0a2d9165ba9aa704f4b9f33e85f7e8c2": 0.7,  # sycamore.h
    # "0xe1ba9248dd9f6631fa09ee65b53a669774d8fdb1": 0.7,  # zoidberg
    # "0xa569c2fc7757a0235bb02de7897a715536ebc698": 0.95,  # lucjan-provider-1
    # "0xcb9937af44f0cff6c1f72e7fe4b88dd8593a46ca": 0.95,  # lucjan-provider-2
}


async def select_proposal(proposal: Proposal) -> Optional[float]:
    data = await proposal.get_data()
    if data.issuer_id is None:
        return None
    
    score = PROVIDER_SCORES.get(data.issuer_id, None)
    print(
        f"Scoring {score} proposal from {data.properties.get('golem.node.id.name')} - {data.issuer_id}"
    )
    return score


async def run_hello(activity: Activity) -> str:
    assert activity.idle, f"Got a non-idle activity {activity}"
    batch = await activity.execute_commands(
        commands.Deploy(),
        commands.Start(),
        commands.Run(["/bin/echo", "-n", f"Hello from {activity}"]),
    )
    await batch.wait(timeout=10)

    result = batch.events[-1].stdout
    assert (
        result is not None and "Hello from" in result
    ), f"Got an incorrect result from {activity}: {result}"

    return result


async def on_exception(func: Callable, args: Tuple, e: Exception) -> None:
    activity = args[0]
    print(f"Activity {activity} failed because of {e}")
    await activity.parent.close_all()


async def main() -> None:
    golem = GolemNode()
    golem.event_bus.listen(DefaultLogger().on_event)

    async with golem:
        allocation = await golem.create_allocation(1)
        payment_manager = DefaultPaymentManager(golem, allocation)
        demand = await golem.create_demand(PAYLOAD, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            SimpleScorer(
                select_proposal,
                min_proposals=SELECT_MIN_PROPOSALS,
                min_wait=SELECT_MIN_TIME,
                max_wait=SELECT_MAX_TIME,
            ),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
            Map(run_hello, on_exception=on_exception),
            Limit(1),
            Buffer(),
        )

        async for result in chain:
            print(f"RESULT: {result}")

        print("TASK DONE")
        await payment_manager.terminate_agreements()
        await payment_manager.wait_for_invoices()


if __name__ == "__main__":
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
