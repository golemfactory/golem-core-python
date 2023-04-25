from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from golem_core.core.golem_node import GolemNode
from golem_core.core.market_api import RepositoryVmPayload
from golem_core.pipeline import Chain, Map
from golem_core.core.market_api.pipeline import (
    default_negotiate,
    default_create_agreement,
    default_create_activity,
)
from golem_core.core.activity_api import Activity

ANY_PAYLOAD = RepositoryVmPayload("9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae")

@asynccontextmanager
async def get_activity(golem: Optional[GolemNode] = None) -> AsyncGenerator[Activity, None]:
    if golem is None:
        golem = GolemNode()

    async with golem:
        allocation = await golem.create_allocation(1)
        demand = await golem.create_demand(ANY_PAYLOAD, allocations=[allocation])

        chain = Chain(
            demand.initial_proposals(),
            Map(default_negotiate),
            Map(default_create_agreement),
            Map(default_create_activity),
        )
        future_activity = await chain.__anext__()
        activity = await future_activity
        print(activity)
        yield activity
