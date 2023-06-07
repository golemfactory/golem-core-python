from abc import ABC, abstractmethod
from ctypes import Union
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, MutableSequence

from golem_core.core.props_cons.base import PropertyPath


class ConstraintException(Exception):
    pass


class ConstraintOperator(StrEnum):
    EQUALS = "="
    GRATER_OR_EQUALS = ">="
    LESS_OR_EQUALS = "<="


class ConstraintGroupOperator(StrEnum):
    AND = "&"
    OR = "|"
    NOT = "!"


@dataclass
class MarketDemandOfferSyntaxElement(ABC):
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
    property_path: PropertyPath
    operator: ConstraintOperator
    value: Any

    def _serialize(self) -> str:
        return f"({self.property_path}{self.operator}{self.value})"


@dataclass
class ConstraintGroup(MarketDemandOfferSyntaxElement):
    items: MutableSequence[Union["ConstraintGroup", Constraint]] = field(default_factory=list)
    operator: ConstraintGroupOperator = "&"

    def _validate(self) -> None:
        if self.operator == "!" and 2 <= len(self.items):
            return ConstraintException("ConstraintGroup with `!` operator can contain only 1 item!")

    def _serialize(self) -> str:
        items_len = len(self.items)

        if items_len == 0:
            return f"({self.operator})"

        if items_len == 1:
            return self.items[0].serialize()

        items = "\n\t".join(item.serialize() for item in self.items)

        return f"({self.operator}{items})"


@dataclass
class Constraints(ConstraintGroup):
    pass
