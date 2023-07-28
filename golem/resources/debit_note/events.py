from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.debit_note.debit_note import DebitNote  # noqa


class NewDebitNote(NewResource["DebitNote"]):
    pass


class DebitNoteDataChanged(ResourceDataChanged["DebitNote"]):
    pass


class DebitNoteClosed(ResourceClosed["DebitNote"]):
    pass
