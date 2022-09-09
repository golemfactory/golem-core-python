from typing import Tuple, TYPE_CHECKING
from datetime import datetime, timezone

if TYPE_CHECKING:
    from golem_api import GolemNode

from .payment import DebitNote, Invoice
from .market import Agreement
from .activity import Activity
from .yagna_event_collector import YagnaEventCollector


class PaymentEventCollector(YagnaEventCollector):
    def __init__(self, node: "GolemNode"):
        self.node = node
        self.min_ts = datetime.now(timezone.utc)

    def _collect_events_kwargs(self):
        return {'after_timestamp': self.min_ts}

    async def _process_event(self, event):
        self.min_ts = max(event.event_date, self.min_ts)
        resource, parent_resource = await self._get_event_resources(event)
        resource.add_event(event)
        if resource._parent is None:
            parent_resource.add_child(resource)


class DebitNoteEventCollector(PaymentEventCollector):
    @property
    def _collect_events_func(self):
        return DebitNote._get_api(self.node).get_debit_note_events

    async def _get_event_resources(self, event) -> Tuple[DebitNote, Activity]:
        debit_note = self.node.debit_note(event.debit_note_id)
        await debit_note.get_data()
        activity = self.node.activity(debit_note.data.activity_id)
        return debit_note, activity


class InvoiceEventCollector(PaymentEventCollector):
    @property
    def _collect_events_func(self):
        return Invoice._get_api(self.node).get_invoice_events

    async def _get_event_resources(self, event) -> Tuple[Invoice, Agreement]:
        invoice = self.node.invoice(event.invoice_id)
        await invoice.get_data()
        agreement = self.node.agreement(invoice.data.agreement_id)
        return invoice, agreement
