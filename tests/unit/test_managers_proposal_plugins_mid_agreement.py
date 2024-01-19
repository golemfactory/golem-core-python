from datetime import datetime, timedelta
from typing import Optional

import pytest

from golem.managers import MidAgreementPaymentsNegotiator, RejectProposal
from golem.managers.proposal.plugins.negotiating.mid_agreement_payments import (
    DEBIT_NOTE_INTERVAL,
    PAYMENT_TIMEOUT,
)
from golem.payload import Constraints, Properties
from golem.resources import DemandData, ProposalData
from golem.resources.proposal.data import ProposalState


@pytest.mark.parametrize(
    "proposal_state, offered_note_interval, demand_debit_note_interval,"
    "min_demand_debit_note_interval, optimal_debit_note_interval, expected_debit_note_interval,"
    "offer_payment_timeout, demand_payment_timeout, min_demand_payment_timeout,"
    "optimal_payment_timeout, expected_payment_timeout",
    (
        # First values match optimal values
        ("Initial", 120, None, 60, 180, 180, 120, None, 120, 1800, 1800),
        ("Initial", 120, 180, 60, 180, 180, 120, 1800, 120, 1800, 1800),
        ("Draft", 120, None, 60, 180, 180, 120, None, 120, 1800, 1800),
        # New values are using at adjustment_factor to generate new values
        ("Draft", 120, 180, 60, 180, 160, 120, 1800, 120, 1800, 1245),
        # New values are at least lower by min_adjustment[1]
        ("Draft", 120, 121, 60, 180, 120, 1200, 1100, 120, 1800, 1200),
        # New values are not lower then minimal
        ("Draft", 120, 120, 60, 180, 120, 1200, 1100, 120, 1800, 1200),
        # Offered properties are longer then Optimal
        ("Draft", 1200, 180, 60, 600, 1200, 120, 1800, 120, 1800, 1245),
        ("Draft", 120, 180, 60, 600, 160, 12000, 1800, 120, 1800, 12000),
    ),
)
async def test_add_mid_agreement_payments_plugin_ok(
    proposal_state: ProposalState,
    offered_note_interval: int,
    demand_debit_note_interval: Optional[int],
    min_demand_debit_note_interval: int,
    optimal_debit_note_interval: int,
    expected_debit_note_interval: int,
    offer_payment_timeout: int,
    demand_payment_timeout: Optional[int],
    min_demand_payment_timeout: int,
    optimal_payment_timeout: int,
    expected_payment_timeout: int,
):
    plugin = MidAgreementPaymentsNegotiator(
        min_debit_note_interval=timedelta(seconds=min_demand_debit_note_interval),
        optimal_debit_note_interval=timedelta(seconds=optimal_debit_note_interval),
        min_payment_timeout=timedelta(seconds=min_demand_payment_timeout),
        optimal_payment_timeout=timedelta(seconds=optimal_payment_timeout),
    )
    given_proposal_data = ProposalData(
        properties=Properties(
            {
                DEBIT_NOTE_INTERVAL: offered_note_interval,
                PAYMENT_TIMEOUT: offer_payment_timeout,
            }
        ),
        constraints=Constraints(),
        state=proposal_state,
        timestamp=datetime.utcnow(),
        proposal_id=None,
        issuer_id=None,
        prev_proposal_id=None,
    )
    given_demand_data = DemandData(
        properties=Properties(
            {
                DEBIT_NOTE_INTERVAL: demand_debit_note_interval,
                PAYMENT_TIMEOUT: demand_payment_timeout,
            }
        ),
        constraints=Constraints(),
        timestamp=datetime.utcnow(),
        demand_id=None,
        requestor_id=None,
    )

    await plugin(demand_data=given_demand_data, proposal_data=given_proposal_data)

    assert given_demand_data.properties.get(DEBIT_NOTE_INTERVAL) == expected_debit_note_interval
    assert given_demand_data.properties.get(PAYMENT_TIMEOUT) == expected_payment_timeout


@pytest.mark.parametrize(
    "offered_note_interval, demand_debit_note_interval, min_demand_debit_note_interval,"
    "optimal_debit_note_interval,"
    "offer_payment_timeout, demand_payment_timeout, min_demand_payment_timeout,"
    "optimal_payment_timeout",
    (
        # Offer doesn't support mid agreement payments
        (None, None, 60, 600, None, None, 600, 86400),
        (120, None, 60, 600, None, None, 600, 86400),
        (None, None, 60, 600, 120, None, 600, 86400),
        # Offered mid agreement properties are too short
        (120, 180, 180, 600, 120, 1800, 120, 1800),
        (120, 180, 60, 600, 120, 600, 600, 1800),
    ),
)
async def test_add_mid_agreement_payments_plugin_reject(
    offered_note_interval: Optional[int],
    demand_debit_note_interval: Optional[int],
    min_demand_debit_note_interval: int,
    optimal_debit_note_interval: int,
    offer_payment_timeout: Optional[int],
    demand_payment_timeout: Optional[int],
    min_demand_payment_timeout: int,
    optimal_payment_timeout: int,
):
    plugin = MidAgreementPaymentsNegotiator(
        min_debit_note_interval=timedelta(seconds=min_demand_debit_note_interval),
        optimal_debit_note_interval=timedelta(seconds=optimal_debit_note_interval),
        min_payment_timeout=timedelta(seconds=min_demand_payment_timeout),
        optimal_payment_timeout=timedelta(seconds=optimal_payment_timeout),
    )
    given_proposal_data = ProposalData(
        properties=Properties(
            {
                DEBIT_NOTE_INTERVAL: offered_note_interval,
                PAYMENT_TIMEOUT: offer_payment_timeout,
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
                DEBIT_NOTE_INTERVAL: demand_debit_note_interval,
                PAYMENT_TIMEOUT: demand_payment_timeout,
            }
        ),
        constraints=Constraints(),
        timestamp=datetime.utcnow(),
        demand_id=None,
        requestor_id=None,
    )

    with pytest.raises(RejectProposal):
        await plugin(demand_data=given_demand_data, proposal_data=given_proposal_data)
