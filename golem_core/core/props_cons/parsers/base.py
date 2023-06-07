from abc import ABC, abstractmethod

from golem_core.core.props_cons.constraints import Constraints


class DemandOfferSyntaxParser(ABC):
    @abstractmethod
    def parse(self, syntax: str) -> Constraints:
        ...
