from datetime import datetime
from enum import Enum

import pytest

from golem.payload import Constraint, ConstraintException, ConstraintGroup, Constraints


class ExampleEnum(Enum):
    FOO = "BAR"


def test_constraints_serialize():
    cons = Constraints(
        [
            Constraint("foo", "=", "bar"),
            Constraint("int_field", "=", 123),
            Constraint("float_field", "=", 1.5),
            Constraint("datetime_field", "=", datetime.fromtimestamp(1672617600)),
            Constraint("enum_field", "=", ExampleEnum.FOO),
            Constraint(
                "list_field",
                "=",
                [
                    datetime.fromtimestamp(1672617600),
                    ExampleEnum.FOO,
                ],
            ),
            Constraint("empty_list", "=", []),
            ConstraintGroup([Constraint("some.other.field", "=", "works!")], "|"),
        ]
    )

    assert cons.serialize() == (
        "(&(foo=bar)\n"
        "\t(int_field=123)\n"
        "\t(float_field=1.5)\n"
        "\t(datetime_field=1672617600000)\n"
        "\t(enum_field=BAR)\n"
        "\t(&(list_field=1672617600000)\n"
        "\t(list_field=BAR))\n"
        "\t(|(some.other.field=works!)))"
    )


def test_constraint_group_raises_on_not_operator_with_multiple_items():
    with pytest.raises(ConstraintException):
        ConstraintGroup(
            [
                Constraint("foo", "=", "bar"),
                Constraint("bat", "=", "man"),
            ],
            "!",
        )

    cons_group = ConstraintGroup(
        [
            Constraint("foo", "=", "bar"),
            Constraint("bat", "=", "man"),
        ]
    )

    cons_group.operator = "!"

    with pytest.raises(ConstraintException):
        cons_group.serialize()
