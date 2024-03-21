from datetime import datetime, timedelta, timezone

import pytest

from golem.resources.debit_note import DebitNote
from golem.resources.exceptions import PaymentValidationException
from golem.resources.utils.payment import PaymentProps


@pytest.mark.parametrize(
    "payment_timeout, grace_period, agreement_duration, previous_payable_debit_notes_count",
    (
        (60, 0, 60, 1),
        (10, 0, 100, 10),
        (600, 0, 6000, 10),
        (600, 600, 6000, 11),  # 600s of grace_period can compensate for 1 extra debit note
    ),
)
def test_validate_mid_agreement_payment_ok(
    payment_timeout, grace_period, agreement_duration, previous_payable_debit_notes_count
):
    given_payment_props = PaymentProps(
        payment_timeout=payment_timeout, debit_notes_accept_timeout=grace_period
    )
    given_payment_due_date = datetime.now(timezone.utc)
    given_agreement_duration = timedelta(seconds=agreement_duration)
    given_previous_payable_debit_notes_count = previous_payable_debit_notes_count
    # no error
    DebitNote.validate_mid_agreement_payment(
        given_payment_props,
        given_payment_due_date,
        given_agreement_duration,
        given_previous_payable_debit_notes_count,
        grace_period=timedelta(seconds=grace_period),
    )


@pytest.mark.parametrize(
    "payment_timeout, grace_period, agreement_duration, previous_payable_debit_notes_count",
    (
        (60, 0, 50, 1),
        (10, 0, 99, 10),
        (10, 0, 100, 11),
        (600, 0, 6000, 11),
        (600, 599, 6000, 11),  # 599 of grace_period cannot compensate for 1 extra debit note
    ),
)
def test_validate_mid_agreement_payment_too_many_debit_notes(
    payment_timeout, grace_period, agreement_duration, previous_payable_debit_notes_count
):
    given_payment_props = PaymentProps(
        payment_timeout=payment_timeout, debit_notes_accept_timeout=grace_period
    )
    given_payment_due_date = datetime.now(timezone.utc)
    given_agreement_duration = timedelta(seconds=agreement_duration)
    given_previous_payable_debit_notes_count = previous_payable_debit_notes_count
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(
            given_payment_props,
            given_payment_due_date,
            given_agreement_duration,
            given_previous_payable_debit_notes_count,
            grace_period=timedelta(seconds=grace_period),
        )


def test_validate_mid_agreement_payment_no_payment_due_date():
    given_payment_props = PaymentProps()
    given_payment_due_date = None
    given_agreement_duration = timedelta(seconds=60)
    given_previous_payable_debit_notes_count = 1
    # no error
    DebitNote.validate_mid_agreement_payment(
        given_payment_props,
        given_payment_due_date,
        given_agreement_duration,
        given_previous_payable_debit_notes_count,
    )


def test_validate_mid_agreement_payment_no_payment_timeout():
    given_payment_props = PaymentProps(payment_timeout=None, debit_notes_accept_timeout=120)
    given_payment_due_date = datetime.now(timezone.utc)
    given_agreement_duration = timedelta(seconds=60)
    given_previous_payable_debit_notes_count = 1
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(
            given_payment_props,
            given_payment_due_date,
            given_agreement_duration,
            given_previous_payable_debit_notes_count,
        )


def test_validate_mid_agreement_payment_no_debit_notes_accept_timeout():
    given_payment_props = PaymentProps(payment_timeout=1200, debit_notes_accept_timeout=None)
    given_payment_due_date = datetime.now(timezone.utc)
    given_agreement_duration = timedelta(seconds=60)
    given_previous_payable_debit_notes_count = 1
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(
            given_payment_props,
            given_payment_due_date,
            given_agreement_duration,
            given_previous_payable_debit_notes_count,
        )
