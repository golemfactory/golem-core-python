import pytest

from golem.payload import (
    Constraint,
    ConstraintException,
    ConstraintGroup,
    SyntaxException,
    TextXPayloadSyntaxParser,
)


@pytest.fixture(scope="module")
def demand_offer_parser():
    return TextXPayloadSyntaxParser()


def test_parse_raises_exception_on_bad_syntax(demand_offer_parser):
    with pytest.raises(SyntaxException):
        demand_offer_parser.parse_constraints("NOT VALID SYNTAX")


@pytest.mark.parametrize(
    "input_string, output",
    (
        ("(foo=1)", Constraint("foo", "=", "1")),
        ("(float.value=1.5)", Constraint("float.value", "=", "1.5")),
        ("(foo=bar)", Constraint("foo", "=", "bar")),
        (
            "(foo=more.complex.value)",
            Constraint("foo", "=", "more.complex.value"),
        ),
        (
            "(foo=http://google.com)",
            Constraint("foo", "=", "http://google.com"),
        ),
        ("(foo=[1, 2, 3])", Constraint("foo", "=", ["1", "2", "3"])),
        ("(foo=[a, b, c])", Constraint("foo", "=", ["a", "b", "c"])),
        ("(some.nested.param=1)", Constraint("some.nested.param", "=", "1")),
        ("(foo<=1)", Constraint("foo", "<=", "1")),
        ("(foo>=1)", Constraint("foo", ">=", "1")),
        ("(foo<1)", Constraint("foo", "<", "1")),
        ("(foo>1)", Constraint("foo", ">", "1")),
    ),
)
def test_single_constraint(demand_offer_parser, input_string, output):
    result = demand_offer_parser.parse_constraints(input_string)

    assert result == output


@pytest.mark.parametrize(
    "input_string, output",
    (
        (
            "(& (foo=1) (bar=1))",
            ConstraintGroup([Constraint("foo", "=", "1"), Constraint("bar", "=", "1")]),
        ),
        (
            "(& (even=1) (more=2) (values=3))",
            ConstraintGroup(
                [
                    Constraint("even", "=", "1"),
                    Constraint("more", "=", "2"),
                    Constraint("values", "=", "3"),
                ]
            ),
        ),
        (
            "(| (foo=1) (bar=2))",
            ConstraintGroup([Constraint("foo", "=", "1"), Constraint("bar", "=", "2")], "|"),
        ),
        (
            "(| (foo=1) (bar=2))",
            ConstraintGroup([Constraint("foo", "=", "1"), Constraint("bar", "=", "2")], "|"),
        ),
    ),
)
def test_constraint_groups(demand_offer_parser, input_string, output):
    result = demand_offer_parser.parse_constraints(input_string)

    assert result == output


@pytest.mark.parametrize(
    "input_string, output",
    (
        ("(&)", ConstraintGroup(operator="&")),
        ("(|)", ConstraintGroup(operator="|")),
        ("(!)", ConstraintGroup(operator="!")),
    ),
)
def test_constraint_groups_empty(demand_offer_parser, input_string, output):
    result = demand_offer_parser.parse_constraints(input_string)

    assert result == output


def test_error_not_operator_with_multiple_items(demand_offer_parser):
    with pytest.raises(ConstraintException):
        demand_offer_parser.parse_constraints("(! (foo=1) (bar=1))")


@pytest.mark.parametrize(
    "input_string, output",
    (
        (
            "(& (& (foo=1) (bar=2)) (baz=3))",
            ConstraintGroup(
                [
                    ConstraintGroup([Constraint("foo", "=", "1"), Constraint("bar", "=", "2")]),
                    Constraint("baz", "=", "3"),
                ]
            ),
        ),
        (
            "(| (& (foo=1) (bar=2)) (& (bat=3) (man=4)))",
            ConstraintGroup(
                [
                    ConstraintGroup([Constraint("foo", "=", "1"), Constraint("bar", "=", "2")]),
                    ConstraintGroup([Constraint("bat", "=", "3"), Constraint("man", "=", "4")]),
                ],
                "|",
            ),
        ),
    ),
)
def test_constraint_groups_nested(demand_offer_parser, input_string, output):
    result = demand_offer_parser.parse_constraints(input_string)

    assert result == output
