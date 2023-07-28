from abc import ABC
from typing import TYPE_CHECKING

from golem.event_bus import Event

if TYPE_CHECKING:
    from golem.node import GolemNode


class GolemNodeEvent(Event, ABC):
    """Base class for all events related to a particular :any:`GolemNode` only."""

    def __init__(self, node: "GolemNode"):
        self._node = node

    @property
    def node(self) -> "GolemNode":
        return self._node

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}({self.node.app_key},"
            f" app_session_id: {self.node.app_session_id})"
        )


class SessionStarted(GolemNodeEvent):
    """Emitted when a :any:`GolemNode` starts operating."""


class ShutdownStarted(GolemNodeEvent):
    """:any:`GolemNode` is closing."""


class ShutdownFinished(GolemNodeEvent):
    """:any:`GolemNode` closed successfully."""
