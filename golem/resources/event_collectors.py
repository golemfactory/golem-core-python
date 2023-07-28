from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Tuple, Union

from ya_payment import models

from golem.resources.base import Resource
from golem.utils.low import YagnaEventCollector

if TYPE_CHECKING:
    from golem.node import GolemNode

InvoiceEvent = Union[
    models.InvoiceReceivedEvent,
    models.InvoiceAcceptedEvent,
    models.InvoiceReceivedEvent,
    models.InvoiceFailedEvent,
    models.InvoiceSettledEvent,
    models.InvoiceCancelledEvent,
]

DebitNoteEvent = Union[
    models.DebitNoteReceivedEvent,
    models.DebitNoteAcceptedEvent,
    models.DebitNoteReceivedEvent,
    models.DebitNoteFailedEvent,
    models.DebitNoteSettledEvent,
    models.DebitNoteCancelledEvent,
]


class PaymentEventCollector(YagnaEventCollector, ABC):
    def __init__(self, node: "GolemNode"):
        self.node = node
        self.min_ts = datetime.now(timezone.utc)

    def _collect_events_kwargs(self) -> Dict:
        return {"after_timestamp": self.min_ts, "app_session_id": self.node.app_session_id}

    async def _process_event(self, event: Union[InvoiceEvent, DebitNoteEvent]) -> None:
        self.min_ts = max(event.event_date, self.min_ts)
        resource, parent_resource = await self._get_event_resources(event)
        resource.add_event(event)
        if resource._parent is None:
            parent_resource.add_child(resource)

    @abstractmethod
    async def _get_event_resources(self, event: Any) -> Tuple[Resource, Resource]:
        raise NotImplementedError
