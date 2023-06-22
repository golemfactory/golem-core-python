from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, MutableSequence, Union

from golem_core.core.props_cons.base import PropertyName, PropsConstrsSerializerMixin


class ConstraintException(Exception):
    pass


ConstraintOperator = Literal["=", "<=", ">=", "<", ">"]
ConstraintGroupOperator = Literal["&", "|", "!"]


@dataclass
class MarketDemandOfferSyntaxElement(PropsConstrsSerializerMixin, ABC):
    def __post_init__(self) -> None:
        self._validate()

    def serialize(self) -> str:
        self._validate()

        return self._serialize()

    @abstractmethod
    def _serialize(self) -> str:
        ...

    def _validate(self) -> None:
        ...


@dataclass
class Constraint(MarketDemandOfferSyntaxElement):
    property_name: PropertyName
    operator: ConstraintOperator
    value: Any

    def _serialize(self) -> str:
        serialized_value = self._serialize_value(self.value)

        if isinstance(self.value, (list, tuple)):
            if not self.value:
                return ""

            serialized_value = "[{}]".format(", ".join(str(v) for v in serialized_value))

        return f"({self.property_name}{self.operator}{serialized_value})"


@dataclass
class ConstraintGroup(MarketDemandOfferSyntaxElement):
    items: MutableSequence[Union["ConstraintGroup", Constraint]] = field(default_factory=list)
    operator: ConstraintGroupOperator = "&"

    def _validate(self) -> None:
        if self.operator == "!" and 2 <= len(self.items):
            raise ConstraintException("ConstraintGroup with `!` operator can contain only 1 item!")

    def _serialize(self) -> str:
        serialized = [item.serialize() for item in self.items]
        items = "\n\t".join(s for s in serialized if s)

        return f"({self.operator}{items})"


@dataclass
class Constraints(ConstraintGroup):
    pass
