from datetime import datetime
from enum import Enum

from golem.payload import Properties


class ExampleEnum(Enum):
    FOO = "BAR"


def test_property_deepcopies_its_input():
    list_field = [1, 2, 3]
    original_dict = {
        "foo": "bar",
        "list_field": list_field,
    }
    props = Properties(original_dict)

    assert props["foo"] == "bar"
    assert props["list_field"][0] == 1
    assert props["list_field"][1] == 2
    assert props["list_field"][2] == 3

    props["foo"] = "123"
    props["list_field"].append(4)

    assert props["foo"] == "123"
    assert props["list_field"] == [1, 2, 3, 4]

    assert original_dict["foo"] == "bar"
    assert original_dict["list_field"] != props["list_field"]


def test_property_serialize():
    props = Properties(
        {
            "foo": "bar",
            "int_field": 123,
            "float_field": 1.5,
            "datetime_field": datetime(2023, 1, 2),
            "enum_field": ExampleEnum.FOO,
            "list_field": [
                datetime(2023, 1, 2),
                ExampleEnum.FOO,
            ],
            "nulled_field": None,
        }
    )

    serialized_props = props.serialize()

    assert serialized_props == {
        "foo": "bar",
        "int_field": 123,
        "float_field": 1.5,
        "datetime_field": 1672614000000,
        "enum_field": "BAR",
        "list_field": [
            1672614000000,
            "BAR",
        ],
    }
