from abc import ABC, abstractmethod

from golem.payload.constraints import Constraints


class SyntaxException(Exception):
    pass


class BasePayloadSyntaxParser(ABC):
    @abstractmethod
    def parse_constraints(self, syntax: str) -> Constraints:
        ...
