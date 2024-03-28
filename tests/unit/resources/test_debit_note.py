from datetime import datetime, timedelta, timezone

import pytest

from golem.resources.debit_note import DebitNote
from golem.resources.exceptions import PaymentValidationException
from golem.resources.utils.payment import PaymentProps


@pytest.mark.parametrize(
    "activity_offset, payment_timeout_s, debit_note_interval_s, payment_due_date_in, "
    "previous_debit_note_offset, previous_payable_debit_note_offset, grace_period",
    (
        (
            timedelta(seconds=900),
            600,
            60,
            timedelta(seconds=600),
            timedelta(seconds=60),
            timedelta(seconds=600),
            timedelta(seconds=0),
        ),
        (
            timedelta(hours=1),
            600,
            60,
            timedelta(seconds=700),
            timedelta(seconds=120),
            timedelta(seconds=700),
            timedelta(seconds=0),
        ),
        (
            timedelta(seconds=900),
            600,
            60,
            timedelta(seconds=570),
            timedelta(seconds=30),
            timedelta(seconds=570),
            timedelta(seconds=30),
        ),
    ),
)
def test_validate_mid_agreement_payment_ok(
    activity_offset,
    payment_timeout_s,
    debit_note_interval_s,
    payment_due_date_in,
    previous_debit_note_offset,
    previous_payable_debit_note_offset,
    grace_period,
):
    now = datetime.now(timezone.utc)
    given_activity_created_at = now - activity_offset
    given_debit_note_created_at = now
    given_payment_props = PaymentProps(
        payment_timeout=payment_timeout_s, debit_note_interval=debit_note_interval_s
    )
    given_payment_due_date = now + payment_due_date_in
    given_previous_debit_note_created_at = now - previous_debit_note_offset
    given_previous_payable_debit_note_created_at = now - previous_payable_debit_note_offset
    given_payment_timeout_grace_period = grace_period
    given_debit_note_interval_grace_period = grace_period
    # no error
    DebitNote.validate_mid_agreement_payment(
        given_activity_created_at,
        given_debit_note_created_at,
        given_payment_props,
        given_payment_due_date,
        given_previous_debit_note_created_at,
        given_previous_payable_debit_note_created_at,
        given_payment_timeout_grace_period,
        given_debit_note_interval_grace_period,
    )


@pytest.mark.parametrize(
    "activity_offset, payment_timeout_s, debit_note_interval_s, payment_due_date_in, "
    "grace_period",
    (
        (
            timedelta(seconds=600),
            600,
            60,
            timedelta(seconds=600),
            timedelta(seconds=0),
        ),
        (
            timedelta(hours=1),
            600,
            60,
            timedelta(seconds=700),
            timedelta(seconds=0),
        ),
        (
            timedelta(seconds=570),
            600,
            60,
            timedelta(seconds=570),
            timedelta(seconds=30),
        ),
    ),
)
def test_validate_mid_agreement_payment_first_debit_note_ok(
    activity_offset,
    payment_timeout_s,
    debit_note_interval_s,
    payment_due_date_in,
    grace_period,
):
    now = datetime.now(timezone.utc)
    given_activity_created_at = now - activity_offset
    given_debit_note_created_at = now
    given_payment_props = PaymentProps(
        payment_timeout=payment_timeout_s, debit_note_interval=debit_note_interval_s
    )
    given_payment_due_date = now + payment_due_date_in
    given_payment_timeout_grace_period = grace_period
    given_debit_note_interval_grace_period = grace_period
    # no error
    DebitNote.validate_mid_agreement_payment(
        given_activity_created_at,
        given_debit_note_created_at,
        given_payment_props,
        given_payment_due_date,
        payment_timeout_grace_period=given_payment_timeout_grace_period,
        debit_note_interval_grace_period=given_debit_note_interval_grace_period,
    )


@pytest.mark.parametrize(
    "activity_offset, payment_timeout_s, debit_note_interval_s, payment_due_date_in, "
    "previous_debit_note_offset, previous_payable_debit_note_offset, grace_period",
    (
        (
            timedelta(seconds=900),
            600,
            60,
            timedelta(seconds=500),
            timedelta(seconds=60),
            timedelta(seconds=600),
            timedelta(seconds=0),
        ),
        (
            timedelta(seconds=900),
            600,
            60,
            timedelta(seconds=600),
            timedelta(seconds=45),
            timedelta(seconds=600),
            timedelta(seconds=0),
        ),
        (
            timedelta(seconds=900),
            600,
            60,
            timedelta(seconds=600),
            timedelta(seconds=60),
            timedelta(seconds=500),
            timedelta(seconds=0),
        ),
        (
            timedelta(seconds=900),
            600,
            60,
            timedelta(seconds=500),
            timedelta(seconds=60),
            timedelta(seconds=600),
            timedelta(seconds=30),
        ),
    ),
)
def test_validate_mid_agreement_payment_errors(
    activity_offset,
    payment_timeout_s,
    debit_note_interval_s,
    payment_due_date_in,
    previous_debit_note_offset,
    previous_payable_debit_note_offset,
    grace_period,
):
    now = datetime.now(timezone.utc)
    given_activity_created_at = now - activity_offset
    given_debit_note_created_at = now
    given_payment_props = PaymentProps(
        payment_timeout=payment_timeout_s, debit_note_interval=debit_note_interval_s
    )
    given_payment_due_date = now + payment_due_date_in
    given_previous_debit_note_created_at = now - previous_debit_note_offset
    given_previous_payable_debit_note_created_at = now - previous_payable_debit_note_offset
    given_payment_timeout_grace_period = grace_period
    given_debit_note_interval_grace_period = grace_period
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(
            given_activity_created_at,
            given_debit_note_created_at,
            given_payment_props,
            given_payment_due_date,
            given_previous_debit_note_created_at,
            given_previous_payable_debit_note_created_at,
            given_payment_timeout_grace_period,
            given_debit_note_interval_grace_period,
        )


@pytest.mark.parametrize(
    "activity_offset, payment_timeout_s, debit_note_interval_s, payment_due_date_in, "
    "grace_period",
    (
        (
            timedelta(seconds=590),
            600,
            60,
            timedelta(seconds=600),
            timedelta(seconds=0),
        ),
        (
            timedelta(seconds=590),
            600,
            60,
            timedelta(seconds=590),
            timedelta(seconds=0),
        ),
        (
            timedelta(seconds=600),
            600,
            60,
            timedelta(seconds=500),
            timedelta(seconds=30),
        ),
        (
            timedelta(seconds=500),
            600,
            60,
            timedelta(seconds=600),
            timedelta(seconds=30),
        ),
    ),
)
def test_validate_mid_agreement_payment_first_debit_note_errors(
    activity_offset,
    payment_timeout_s,
    debit_note_interval_s,
    payment_due_date_in,
    grace_period,
):
    now = datetime.now(timezone.utc)
    given_activity_created_at = now - activity_offset
    given_debit_note_created_at = now
    given_payment_props = PaymentProps(
        payment_timeout=payment_timeout_s, debit_note_interval=debit_note_interval_s
    )
    given_payment_due_date = now + payment_due_date_in
    given_payment_timeout_grace_period = grace_period
    given_debit_note_interval_grace_period = grace_period
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(
            given_activity_created_at,
            given_debit_note_created_at,
            given_payment_props,
            given_payment_due_date,
            payment_timeout_grace_period=given_payment_timeout_grace_period,
            debit_note_interval_grace_period=given_debit_note_interval_grace_period,
        )


def test_validate_mid_agreement_payment_no_payment_due_date():
    given_payment_props = PaymentProps(payment_timeout=600, debit_note_interval=60)
    given_payment_due_date = None
    # no error
    DebitNote.validate_mid_agreement_payment(
        payment_props=given_payment_props,
        payment_due_date=given_payment_due_date,
        activity_created_at=datetime.now(timezone.utc),
        debit_note_created_at=datetime.now(timezone.utc),
    )


def test_validate_mid_agreement_payment_no_payment_timeout():
    given_payment_props = PaymentProps(payment_timeout=None, debit_note_interval=60)
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(
            payment_props=given_payment_props,
            activity_created_at=datetime.now(timezone.utc),
            debit_note_created_at=datetime.now(timezone.utc),
            payment_due_date=datetime.now(timezone.utc),
        )


def test_validate_mid_agreement_payment_no_debit_note_interval():
    given_payment_props = PaymentProps(payment_timeout=600, debit_note_interval=None)
    with pytest.raises(PaymentValidationException):
        DebitNote.validate_mid_agreement_payment(
            payment_props=given_payment_props,
            activity_created_at=datetime.now(timezone.utc),
            debit_note_created_at=datetime.now(timezone.utc),
            payment_due_date=datetime.now(timezone.utc),
        )
