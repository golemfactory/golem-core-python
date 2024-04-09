from datetime import timedelta
from decimal import Decimal

import pytest

from golem.resources.exceptions import PaymentValidationException
from golem.resources.utils.infrastructure import InfrastructureProps
from golem.resources.utils.payment import (
    LinearCoeffs,
    validate_payment_calculated_cost,
    validate_payment_max_cost,
)


def test_validate_payment_max_cost_ok():
    given_coeffs = LinearCoeffs(
        price_cpu_sec=Decimal("1.0"),
        price_duration_sec=Decimal("1.0"),
        price_initial=Decimal("1.0"),
        usage_vector=["golem.usage.cpu-sec", "golem.usage.duration-sec"],
    )
    given_inf = InfrastructureProps(cpu_threads=2, memory_gib=0.0, storage_gib=0.0)
    given_duration = timedelta(seconds=60)
    given_amount = Decimal(181)
    received_max_cost, received_max_cost_since_last_debit_note = validate_payment_max_cost(
        coeffs=given_coeffs,
        inf=given_inf,
        duration=given_duration,
        amount=given_amount,
        grace_period=timedelta(),
    )
    assert received_max_cost == Decimal(181)
    assert received_max_cost_since_last_debit_note is None


def test_validate_payment_max_cost_payment_validation_exception():
    given_coeffs = LinearCoeffs(
        price_cpu_sec=Decimal("1.0"),
        price_duration_sec=Decimal("1.0"),
        price_initial=Decimal("1.0"),
        usage_vector=["golem.usage.cpu-sec", "golem.usage.duration-sec"],
    )
    given_inf = InfrastructureProps(cpu_threads=2, memory_gib=0.0, storage_gib=0.0)
    given_duration = timedelta(seconds=60)
    given_amount = Decimal(190)
    with pytest.raises(PaymentValidationException):
        validate_payment_max_cost(
            coeffs=given_coeffs,
            inf=given_inf,
            duration=given_duration,
            amount=given_amount,
            grace_period=timedelta(),
        )


def test_validate_payment_max_cost_last_debit_note_ok():
    given_coeffs = LinearCoeffs(
        price_cpu_sec=Decimal("1.0"),
        price_duration_sec=Decimal("1.0"),
        price_initial=Decimal("1.0"),
        usage_vector=["golem.usage.cpu-sec", "golem.usage.duration-sec"],
    )
    given_inf = InfrastructureProps(cpu_threads=2, memory_gib=0.0, storage_gib=0.0)
    given_duration = timedelta(seconds=60)
    given_amount = Decimal(181)
    given_time_since_last_debit_note = timedelta(seconds=10)
    given_amount_since_last_debit_note = Decimal(31)
    received_max_cost, received_max_cost_since_last_debit_note = validate_payment_max_cost(
        coeffs=given_coeffs,
        inf=given_inf,
        duration=given_duration,
        amount=given_amount,
        time_since_last_debit_note=given_time_since_last_debit_note,
        amount_since_last_debit_note=given_amount_since_last_debit_note,
        grace_period=timedelta(),
    )
    assert received_max_cost == Decimal(181)
    assert received_max_cost_since_last_debit_note is not None


def test_validate_payment_max_cost_last_debit_note_payment_validation_exception():
    given_coeffs = LinearCoeffs(
        price_cpu_sec=Decimal("1.0"),
        price_duration_sec=Decimal("1.0"),
        price_initial=Decimal("1.0"),
        usage_vector=["golem.usage.cpu-sec", "golem.usage.duration-sec"],
    )
    given_inf = InfrastructureProps(cpu_threads=2, memory_gib=0.0, storage_gib=0.0)
    given_duration = timedelta(seconds=60)
    given_amount = Decimal(181)
    given_time_since_last_debit_note = timedelta(seconds=10)
    given_amount_since_last_debit_note = Decimal(32)
    with pytest.raises(PaymentValidationException):
        validate_payment_max_cost(
            coeffs=given_coeffs,
            inf=given_inf,
            duration=given_duration,
            amount=given_amount,
            time_since_last_debit_note=given_time_since_last_debit_note,
            amount_since_last_debit_note=given_amount_since_last_debit_note,
            grace_period=timedelta(),
        )


def test_validate_payment_calculated_cost_ok():
    given_coeffs = LinearCoeffs(
        price_cpu_sec=Decimal("1.0"),
        price_duration_sec=Decimal("1.0"),
        price_initial=Decimal("1.0"),
        usage_vector=["golem.usage.cpu-sec", "golem.usage.duration-sec"],
    )
    given_usage_counter_vector = [120, 60]
    """120 cps s + 60s of duration, both priced at 1GLM/s + 1 GLM of initial price = 181 GLM
    """
    given_amount = Decimal(181)

    received_calculated_cost = validate_payment_calculated_cost(
        coeffs=given_coeffs,
        amount=given_amount,
        usage_counter_vector=given_usage_counter_vector,
    )
    assert received_calculated_cost == Decimal(181)


def test_validate_payment_calculated_cost_payment_validation_exception():
    given_coeffs = LinearCoeffs(
        price_cpu_sec=Decimal("1.0"),
        price_duration_sec=Decimal("1.0"),
        price_initial=Decimal("1.0"),
        usage_vector=["golem.usage.cpu-sec", "golem.usage.duration-sec"],
    )
    given_usage_counter_vector = [120, 60]
    """120 cps s + 60s of duration, both priced at 1GLM/s + 1 GLM of initial price = 181 GLM
    """
    given_amount = Decimal(190)

    with pytest.raises(PaymentValidationException):
        validate_payment_calculated_cost(
            coeffs=given_coeffs,
            amount=given_amount,
            usage_counter_vector=given_usage_counter_vector,
        )
