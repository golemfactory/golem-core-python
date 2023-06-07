from golem_core.core.props_cons.constraints import Constraints
from golem_core.core.props_cons.parsers.base import DemandOfferSyntaxParser


class TextXDemandOfferSyntaxParser(DemandOfferSyntaxParser):
    def parse(self, syntax: str) -> Constraints:
        return Constraints()
