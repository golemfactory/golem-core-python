from abc import ABC, abstractmethod

from golem_core.core.props_cons.constraints import Constraints


class SyntaxException(Exception):
    pass


class DemandOfferSyntaxParser(ABC):
    @abstractmethod
    def parse(self, syntax: str) -> Constraints:
        ...
