class NewDebitNote(NewResource["DebitNote"]):
    pass


class DebitNoteDataChanged(ResourceDataChanged["DebitNote"]):
    pass


class DebitNoteClosed(ResourceClosed["DebitNote"]):
    pass
