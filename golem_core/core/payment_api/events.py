from golem_core.core.resources import NewResource, ResourceClosed, ResourceDataChanged


class NewAllocation(NewResource["Allocation"]):
    pass


class AllocationDataChanged(ResourceDataChanged["Allocation"]):
    pass


class AllocationClosed(ResourceClosed["Allocation"]):
    pass


class NewDebitNote(NewResource["DebitNote"]):
    pass


class DebitNoteDataChanged(ResourceDataChanged["DebitNote"]):
    pass


class DebitNoteClosed(ResourceClosed["DebitNote"]):
    pass


class NewInvoice(NewResource["Invoice"]):
    pass


class InvoiceDataChanged(ResourceDataChanged["Invoice"]):
    pass


class InvoiceClosed(ResourceClosed["Invoice"]):
    pass
