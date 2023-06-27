from pathlib import Path

from textx import TextXSyntaxError, metamodel_from_file

from golem.payload.constraints import Constraint, ConstraintGroup, Constraints
from golem.payload.parsers.base import PayloadSyntaxParser, SyntaxException


class TextXPayloadSyntaxParser(PayloadSyntaxParser):
    def __init__(self):
        self._metamodel = metamodel_from_file(str(Path(__file__).with_name("syntax.tx")))
        self._metamodel.register_obj_processors(
            {
                "ConstraintGroup": lambda e: ConstraintGroup(e.items, e.operator),
                "Constraint": lambda e: Constraint(e.property_path, e.operator, e.value),
                "PropertyValueList": lambda e: e.items,
            }
        )

    def parse_constraints(self, syntax: str) -> Constraints:
        try:
            model = self._metamodel.model_from_str(syntax)
        except TextXSyntaxError as e:
            raise SyntaxException(f"Syntax `{syntax}` parsed with following error: {e}")

        return model.constraints
