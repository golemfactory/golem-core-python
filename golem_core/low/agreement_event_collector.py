from typing import Callable, Dict, TYPE_CHECKING, Union
from datetime import datetime, timezone

from ya_market import models

from .market import Agreement
from .yagna_event_collector import YagnaEventCollector

if TYPE_CHECKING:
    from golem_core import GolemNode

AgreementEvent = Union[
    models.AgreementApprovedEvent,  # type: ignore  # mypy, why? this class exists
    models.AgreementRejectedEvent,
    models.AgreementCancelledEvent,
    models.AgreementTerminatedEvent,
]

class AgreementEventCollector(YagnaEventCollector):
    """NOTE: this doesn't work now (because of https://github.com/golemfactory/yagna-sdk-team/issues/232)

    (and might not work after the referenced issue is done, because was never properly tested)
    """
    def __init__(self, node: "GolemNode"):
        self.node = node
        self.min_ts = datetime.now(timezone.utc)

    async def _process_event(self, event: AgreementEvent) -> None:
        #   TODO: mypy complains about this, **but** this is correct e.g. for
        #         payment events --> it seems this is yet another ya_client problem
        self.min_ts = max(event.event_date, self.min_ts)
        print("GOT AGREEMENT EVENT!")
        print(event)
        #   FIXME: add event to agreement.events

    @property
    def _collect_events_func(self) -> Callable:
        return Agreement._get_api(self.node).collect_agreement_events

    def _collect_events_kwargs(self) -> Dict:
        return {
            'after_timestamp': self.min_ts,
            'app_session_id': self.node.app_session_id,
            'timeout': 5,
        }
