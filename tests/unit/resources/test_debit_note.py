from datetime import datetime, timedelta

import pytest

from golem.resources.debit_note import DebitNote
from golem.resources.exceptions import PaymentValidationException
from golem.resources.utils.payment import PaymentProps


def test_validate_mid_agreement_payment_ok():
    given_payment_props = PaymentProps(payment_timeout=1200, debit_notes_accept_timeout=120)
    given_payment_due_date = datetime.utcnow()
    # no error
    DebitNote.validate_mid_agreement_payment(given_payment_props, given_payment_due_date)


def test_validate_mid_agreement_payment_no_payment_due_date():
    given_payment_props = PaymentProps()
    given_payment_due_date = None
    # no error
    DebitNote.validate_mid_agreement_payment(given_payment_props, given_payment_due_date)


def test_validate_mid_agreement_payment_no_payment_timeout():
    given_payment_props = PaymentProps(payment_timeout=None, debit_notes_accept_timeout=120)
    given_payment_due_date = datetime.utcnow()
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(given_payment_props, given_payment_due_date)


def test_validate_mid_agreement_payment_no_debit_notes_accept_timeout():
    given_payment_props = PaymentProps(payment_timeout=1200, debit_notes_accept_timeout=None)
    given_payment_due_date = datetime.utcnow()
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(given_payment_props, given_payment_due_date)


def test_validate_debit_notes_frequency_ok():
    given_payment_props = PaymentProps(debit_notes_accept_timeout=60)
    given_agreement_duration = timedelta(minutes=10)
    given_previous_debit_notes_count = 10

    DebitNote.validate_debit_notes_frequency(
        given_payment_props, given_agreement_duration, given_previous_debit_notes_count
    )


def test_validate_debit_notes_frequency_missing_property():
    given_payment_props = PaymentProps(debit_notes_accept_timeout=None)
    given_agreement_duration = timedelta(minutes=10)
    given_previous_debit_notes_count = 10

    with pytest.raises(PaymentValidationException):
        DebitNote.validate_debit_notes_frequency(
            given_payment_props, given_agreement_duration, given_previous_debit_notes_count
        )


def test_validate_debit_notes_frequency_too_many_debit_notes():
    given_payment_props = PaymentProps(debit_notes_accept_timeout=60)
    given_agreement_duration = timedelta(minutes=10)
    given_previous_debit_notes_count = 11

    with pytest.raises(PaymentValidationException):
        DebitNote.validate_debit_notes_frequency(
            given_payment_props, given_agreement_duration, given_previous_debit_notes_count
        )
