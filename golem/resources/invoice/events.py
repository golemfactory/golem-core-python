from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.invoice.invoice import Invoice  # noqa


class NewInvoice(NewResource["Invoice"]):
    pass


class InvoiceDataChanged(ResourceDataChanged["Invoice"]):
    pass


class InvoiceClosed(ResourceClosed["Invoice"]):
    pass
