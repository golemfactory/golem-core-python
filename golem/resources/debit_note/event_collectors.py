from typing import TYPE_CHECKING, Callable, Tuple

from golem.resources.debit_note import DebitNote
from golem.resources.event_collectors import DebitNoteEvent, PaymentEventCollector

if TYPE_CHECKING:
    from golem.resources.activity import Activity


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
