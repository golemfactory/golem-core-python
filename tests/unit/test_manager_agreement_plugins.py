import pytest

from golem.managers.agreement.plugins import PropertyValueLerpScore, RandomScore


@pytest.mark.parametrize(
    "kwargs, property_value, expected",
    (
        (dict(zero_at=0, one_at=1), 0.5, 0.5),
        (dict(zero_at=0, one_at=2), 1, 0.5),
        (dict(zero_at=0, one_at=100), 25, 0.25),
        (dict(zero_at=0, one_at=100), -1, 0),
        (dict(zero_at=0, one_at=100), 200, 1),
        (dict(zero_at=-10, one_at=10), 0, 0.5),
        (dict(zero_at=-10, one_at=10), -10, 0),
        (dict(minus_one_at=10, zero_at=0), 10, -1),
        (dict(minus_one_at=10, zero_at=0), 5, -0.5),
        (dict(minus_one_at=-1, one_at=1), 0, 0),
        (dict(minus_one_at=-1, one_at=1), -0.5, -0.5),
        (dict(minus_one_at=0, one_at=100), 50, 0),
        (dict(minus_one_at=0, one_at=100), 500, 1),
        (dict(minus_one_at=0, one_at=100), -500, -1),
        (dict(minus_one_at=0, one_at=100), -500, -1),
    ),
)
def test_linear_score_plugin(kwargs, property_value, expected, mocker):
    property_name = "some.property"
    proposal_id = "foo"

    scorer = PropertyValueLerpScore(property_name=property_name, **kwargs)
    proposal_data = mocker.Mock(proposal_id=proposal_id, properties={property_name: property_value})

    result = scorer([proposal_data])

    assert result[0] == expected


@pytest.mark.parametrize("expected_value", (0.876, 0.0, 0.2, 0.5, 1))
def test_random_score_plugin(mocker, expected_value):
    mocker.patch(
        "golem.managers.agreement.plugins.random", mocker.Mock(return_value=expected_value)
    )

    proposal_id = "foo"

    scorer = RandomScore()
    proposal_data = mocker.Mock(proposal_id=proposal_id)

    result = scorer([proposal_data])

    assert result[0] == expected_value
