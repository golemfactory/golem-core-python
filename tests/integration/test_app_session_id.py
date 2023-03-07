import pytest
import asyncio

from golem_core import GolemNode
from golem_core.events import ResourceEvent
from golem_core.low import DebitNote, Invoice

from .helpers import get_activity




@pytest.mark.parametrize("kwargs, has_events", (
    ({"app_session_id": "0"}, True),
    ({"app_session_id": None}, True),
    ({}, False),
    ({"app_session_id": "1"}, False),
))
@pytest.mark.asyncio
async def test_app_session_id(kwargs: dict, has_events: bool) -> None:
    events = []

    async def save_event(event: ResourceEvent) -> None:
        events.append(event)

    golem = GolemNode(**kwargs)
    golem.event_bus.resource_listen(save_event)

    async with golem:
        other_golem = GolemNode(app_session_id="0")
        async with get_activity(other_golem):
            pass

        #   TODO: This is not great because test might sometimes fail when there is
        #         a network delay, and usually it will take too long.
        #         This can be improved: don't wait a fixed time, only wait until
        #         `other_golem` got expected events.
        await asyncio.sleep(3)

    if has_events:
        assert any(isinstance(event.resource, DebitNote) for event in events)
        assert any(isinstance(event.resource, Invoice) for event in events)
    else:
        assert all(not isinstance(event.resource, DebitNote) for event in events)
        assert all(not isinstance(event.resource, Invoice) for event in events)
