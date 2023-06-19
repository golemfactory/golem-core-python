from pathlib import Path

from textx import TextXSyntaxError, metamodel_from_file

from golem_core.core.props_cons.constraints import Constraint, ConstraintGroup, Constraints
from golem_core.core.props_cons.parsers.base import DemandOfferSyntaxParser, SyntaxException


class TextXDemandOfferSyntaxParser(DemandOfferSyntaxParser):
    def __init__(self):
        self._metamodel = metamodel_from_file(str(Path(__file__).with_name("syntax.tx")))
        self._metamodel.register_obj_processors(
            {
                "ConstraintGroup": lambda e: ConstraintGroup(e.items, e.operator),
                "Constraint": lambda e: Constraint(e.property_path, e.operator, e.value),
                "PropertyValueList": lambda e: e.items,
            }
        )

    def parse(self, syntax: str) -> Constraints:
        try:
            model = self._metamodel.model_from_str(syntax)
        except TextXSyntaxError as e:
            raise SyntaxException(f"Syntax `{syntax}` parsed with following error: {e}")

        return model.constraints
