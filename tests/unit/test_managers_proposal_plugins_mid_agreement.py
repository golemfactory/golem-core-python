from datetime import datetime, timedelta
from typing import Optional

import pytest

from golem.managers import AddMidAgreementPayments, RejectProposal
from golem.payload import Constraints, Properties
from golem.resources import DemandData, ProposalData


@pytest.mark.parametrize(
    "offer_debit_note_interval, demand_debit_note_interval, min_demand_debit_note_interval,"
    "max_demand_debit_note_interval, expected_debit_note_interval,"
    "offer_payment_timeout, demand_payment_timeout, min_demand_payment_timeout,"
    "max_demand_payment_timeout, expected_payment_timeout",
    (
        (120, None, 60, 180, 180, 120, None, 120, 1800, 1800),
        (120, 180, 60, 180, 160, 120, 1800, 120, 1800, 1240),
        (120, 160, 60, 180, 147, 120, 1240, 120, 1800, 867),
        (120, 147, 60, 180, 138, 120, 867, 120, 1800, 618),
        (120, 138, 60, 180, 132, 120, 618, 120, 1800, 452),
        (120, 132, 60, 180, 127, 120, 452, 120, 1800, 342),
        (120, 127, 60, 180, 122, 120, 342, 120, 1800, 268),
        (120, 122, 60, 180, 120, 120, 268, 120, 1800, 219),
        (120, 120, 60, 180, 120, 120, 219, 120, 1800, 186),
        (120, 120, 60, 180, 120, 1200, 1100, 120, 1800, 1200),
    ),
)
async def test_add_mid_agreement_payments_plugin_ok(
    offer_debit_note_interval: int,
    demand_debit_note_interval: Optional[int],
    min_demand_debit_note_interval: int,
    max_demand_debit_note_interval: int,
    expected_debit_note_interval: int,
    offer_payment_timeout: int,
    demand_payment_timeout: Optional[int],
    min_demand_payment_timeout: int,
    max_demand_payment_timeout: int,
    expected_payment_timeout: int,
):
    plugin = AddMidAgreementPayments(
        min_demand_debit_note_interval=timedelta(seconds=min_demand_debit_note_interval),
        max_demand_debit_note_interval=timedelta(seconds=max_demand_debit_note_interval),
        min_demand_payment_timeout=timedelta(seconds=min_demand_payment_timeout),
        max_demand_payment_timeout=timedelta(seconds=max_demand_payment_timeout),
    )
    given_proposal_data = ProposalData(
        properties=Properties(
            {
                "golem.com.scheme.payu.debit-note.interval-sec?": offer_debit_note_interval,
                "golem.com.scheme.payu.payment-timeout-sec?": offer_payment_timeout,
            }
        ),
        constraints=Constraints(),
        state="Draft",
        timestamp=datetime.utcnow(),
        proposal_id=None,
        issuer_id=None,
        prev_proposal_id=None,
    )
    given_demand_data = DemandData(
        properties=Properties(
            {
                "golem.com.scheme.payu.debit-note.interval-sec?": demand_debit_note_interval,
                "golem.com.scheme.payu.payment-timeout-sec?": demand_payment_timeout,
            }
        ),
        constraints=Constraints(),
        timestamp=datetime.utcnow(),
        demand_id=None,
        requestor_id=None,
    )

    await plugin(demand_data=given_demand_data, proposal_data=given_proposal_data)

    assert (
        given_demand_data.properties.get("golem.com.scheme.payu.debit-note.interval-sec?")
        == expected_debit_note_interval
    )
    assert (
        given_demand_data.properties.get("golem.com.scheme.payu.payment-timeout-sec?")
        == expected_payment_timeout
    )


@pytest.mark.parametrize(
    "offer_debit_note_interval, demand_debit_note_interval, min_demand_debit_note_interval,"
    "max_demand_debit_note_interval,"
    "offer_payment_timeout, demand_payment_timeout, min_demand_payment_timeout,"
    "max_demand_payment_timeout",
    (
        # Offer doesn't support mid agreement payments
        (None, None, 60, 600, None, None, 600, 86400),
        (120, None, 60, 600, None, None, 600, 86400),
        (None, None, 60, 600, 120, None, 600, 86400),
        # Offered mid agreement properties are too short
        (120, 180, 180, 600, 120, 1800, 120, 1800),
        (120, 180, 60, 600, 120, 600, 600, 1800),
        # Offered mid agreement properties are too long
        (1200, 180, 60, 600, 120, 1800, 120, 1800),
        (120, 180, 60, 600, 12000, 1800, 120, 1800),
    ),
)
async def test_add_mid_agreement_payments_plugin_reject(
    offer_debit_note_interval: Optional[int],
    demand_debit_note_interval: Optional[int],
    min_demand_debit_note_interval: int,
    max_demand_debit_note_interval: int,
    offer_payment_timeout: Optional[int],
    demand_payment_timeout: Optional[int],
    min_demand_payment_timeout: int,
    max_demand_payment_timeout: int,
):
    plugin = AddMidAgreementPayments(
        min_demand_debit_note_interval=timedelta(seconds=min_demand_debit_note_interval),
        max_demand_debit_note_interval=timedelta(seconds=max_demand_debit_note_interval),
        min_demand_payment_timeout=timedelta(seconds=min_demand_payment_timeout),
        max_demand_payment_timeout=timedelta(seconds=max_demand_payment_timeout),
    )
    given_proposal_data = ProposalData(
        properties=Properties(
            {
                "golem.com.scheme.payu.debit-note.interval-sec?": offer_debit_note_interval,
                "golem.com.scheme.payu.payment-timeout-sec?": offer_payment_timeout,
            }
        ),
        constraints=Constraints(),
        state="Draft",
        timestamp=datetime.utcnow(),
        proposal_id=None,
        issuer_id=None,
        prev_proposal_id=None,
    )
    given_demand_data = DemandData(
        properties=Properties(
            {
                "golem.com.scheme.payu.debit-note.interval-sec?": demand_debit_note_interval,
                "golem.com.scheme.payu.payment-timeout-sec?": demand_payment_timeout,
            }
        ),
        constraints=Constraints(),
        timestamp=datetime.utcnow(),
        demand_id=None,
        requestor_id=None,
    )

    with pytest.raises(RejectProposal):
        await plugin(demand_data=given_demand_data, proposal_data=given_proposal_data)
