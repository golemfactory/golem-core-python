from abc import abstractmethod, ABC
from typing import Any, Callable, Dict, Tuple, TYPE_CHECKING, Union
from datetime import datetime, timezone

from ya_payment import models

from golem_core.core.payment_api.resources import DebitNote, Invoice
from golem_core.core.resources import Resource, YagnaEventCollector


if TYPE_CHECKING:
    from golem_core.core.golem_node.golem_node import GolemNode
    from golem_core.core.activity_api import Activity
    from golem_core.core.market_api import Agreement

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
        return {'after_timestamp': self.min_ts, 'app_session_id': self.node.app_session_id}

    async def _process_event(self, event: Union[InvoiceEvent, DebitNoteEvent]) -> None:
        self.min_ts = max(event.event_date, self.min_ts)
        resource, parent_resource = await self._get_event_resources(event)
        resource.add_event(event)
        if resource._parent is None:
            parent_resource.add_child(resource)

    @abstractmethod
    async def _get_event_resources(self, event: Any) -> Tuple[Resource, Resource]:
        """TODO"""


class DebitNoteEventCollector(PaymentEventCollector):
    @property
    def _collect_events_func(self) -> Callable:
        return DebitNote._get_api(self.node).get_debit_note_events

    async def _get_event_resources(self, event: DebitNoteEvent) -> Tuple[DebitNote, "Activity"]:
        assert event.debit_note_id is not None
        debit_note = self.node.debit_note(event.debit_note_id)
        await debit_note.get_data()
        activity = self.node.activity(debit_note.data.activity_id)
        return debit_note, activity


class InvoiceEventCollector(PaymentEventCollector):
    @property
    def _collect_events_func(self) -> Callable:
        return Invoice._get_api(self.node).get_invoice_events

    async def _get_event_resources(self, event: InvoiceEvent) -> Tuple[Invoice, "Agreement"]:
        assert event.invoice_id is not None
        invoice = self.node.invoice(event.invoice_id)
        await invoice.get_data()
        agreement = self.node.agreement(invoice.data.agreement_id)
        return invoice, agreement
