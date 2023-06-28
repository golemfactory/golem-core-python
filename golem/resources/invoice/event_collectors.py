from typing import TYPE_CHECKING, Callable, Tuple

from golem.resources.event_collectors import InvoiceEvent, PaymentEventCollector
from golem.resources.invoice.invoice import Invoice

if TYPE_CHECKING:
    from golem.resources.agreement import Agreement


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
