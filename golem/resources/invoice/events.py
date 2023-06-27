from golem.resources.resources import NewResource, ResourceClosed, ResourceDataChanged


class NewInvoice(NewResource["Invoice"]):
    pass


class InvoiceDataChanged(ResourceDataChanged["Invoice"]):
    pass


class InvoiceClosed(ResourceClosed["Invoice"]):
    pass
