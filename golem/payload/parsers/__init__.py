from golem.payload.parsers.textx import TextXPayloadSyntaxParser
from golem.payload.parsers.base import SyntaxException


class PayloadSyntaxParser(TextXPayloadSyntaxParser):
    ...


__all__ = (
    "PayloadSyntaxParser",
    "SyntaxException",
)
