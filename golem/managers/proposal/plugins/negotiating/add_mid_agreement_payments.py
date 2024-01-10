import logging
from datetime import timedelta
from typing import Optional

from golem.managers.base import ProposalNegotiator, RejectProposal
from golem.resources import DemandData, ProposalData

logger = logging.getLogger(__name__)


class AddMidAgreementPayments(ProposalNegotiator):
    def __init__(
        self,
        min_demand_debit_note_interval: timedelta = timedelta(minutes=1),
        max_demand_debit_note_interval: timedelta = timedelta(minutes=10),
        min_demand_payment_timeout: timedelta = timedelta(minutes=2),
        max_demand_payment_timeout: timedelta = timedelta(hours=24),
    ) -> None:
        self._min_demand_debit_note_interval: int = int(
            min_demand_debit_note_interval.total_seconds()
        )
        self._max_demand_debit_note_interval: int = int(
            max_demand_debit_note_interval.total_seconds()
        )
        self._min_demand_payment_timeout: int = int(min_demand_payment_timeout.total_seconds())
        self._max_demand_payment_timeout: int = int(max_demand_payment_timeout.total_seconds())

    async def __call__(self, demand_data: DemandData, proposal_data: ProposalData) -> None:
        offer_debit_note_interval = proposal_data.properties.get(
            "golem.com.scheme.payu.debit-note.interval-sec?"
        )
        offer_payment_timeout = proposal_data.properties.get(
            "golem.com.scheme.payu.payment-timeout-sec?"
        )
        if offer_debit_note_interval is None or offer_payment_timeout is None:
            raise RejectProposal("Offer doesn't support mid agreement payments")

        demand_debit_note_interval = demand_data.properties.get(
            "golem.com.scheme.payu.debit-note.interval-sec?"
        )
        demand_payment_timeout = demand_data.properties.get(
            "golem.com.scheme.payu.payment-timeout-sec?"
        )

        if (
            offer_debit_note_interval == demand_debit_note_interval
            and offer_payment_timeout == demand_payment_timeout
        ):
            logger.debug(
                "Mid agreement properties negotiation done with debit note interval: "
                f"{offer_debit_note_interval} and  payment timeout: {offer_payment_timeout}"
            )
            return

        demand_data.properties[
            "golem.com.scheme.payu.debit-note.interval-sec?"
        ] = self._calculate_new_value_proposition(
            offer_debit_note_interval,
            demand_debit_note_interval,
            self._min_demand_debit_note_interval,
            self._max_demand_debit_note_interval,
        )
        demand_data.properties[
            "golem.com.scheme.payu.payment-timeout-sec?"
        ] = self._calculate_new_value_proposition(
            offer_payment_timeout,
            demand_payment_timeout,
            self._min_demand_payment_timeout,
            self._max_demand_payment_timeout,
        )
        logger.debug(
            "Ongoing mid agreement properties negotiation with debit note interval: "
            f"{demand_data.properties['golem.com.scheme.payu.debit-note.interval-sec?']}"
            " and payment timeout: "
            f"{demand_data.properties['golem.com.scheme.payu.payment-timeout-sec?']}"
        )
        return

    @staticmethod
    def _calculate_new_value_proposition(
        offer: int, previous_demand: Optional[int], min_demand: int, max_demand: int
    ):
        if offer == previous_demand:
            return offer
        elif previous_demand is None:
            return max_demand
        elif previous_demand == min_demand:
            raise RejectProposal("Offered mid agreement properties are too short")
        elif offer > max_demand:
            raise RejectProposal("Offered mid agreement properties are too long")
        else:
            new_demand = previous_demand - (previous_demand - offer) // 3
            # we make sure that new demand will be lower then the previous one by at least 5
            new_demand = min(new_demand, previous_demand - 5)
            return max(min_demand, new_demand, offer)
