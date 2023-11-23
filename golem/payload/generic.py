from typing import List

from golem.payload.base import Constraints, Payload, Properties
from golem.payload.parser import PayloadSyntaxParser


class GenericPayload(Payload):
    """A generic demand specification implementing the `Payload` interface."""

    def __init__(self, properties: Properties, constraints: Constraints):
        self._properties: Properties = properties
        self._constraints: Constraints = constraints
        super().__init__()

    def _build_properties(self) -> Properties:
        return self._properties

    def _build_constraints(self) -> Constraints:
        return self._constraints

    @classmethod
    def from_raw_api_data(cls, properties: List, constraints: List[str]):
        return cls(
            properties=Properties({prop.key: prop.value for prop in properties}),
            constraints=Constraints(
                [PayloadSyntaxParser.get_instance().parse_constraints(c) for c in constraints]
            ),
        )
