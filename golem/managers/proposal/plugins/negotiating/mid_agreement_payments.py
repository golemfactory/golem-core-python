import logging
import math
from datetime import timedelta
from typing import Optional

from golem.managers.base import ProposalNegotiator, RejectProposal
from golem.resources import DemandData, ProposalData

logger = logging.getLogger(__name__)

DEFAULT_MIN_DEBIT_NOTE_INTERVAL = timedelta(minutes=1)
DEFAULT_OPTIMAL_DEBIT_NOTE_INTERVAL = timedelta(minutes=10)
DEFAULT_MIN_PAYMENT_TIMEOUT = timedelta(minutes=2)
DEFAULT_OPTIMAL_PAYMENT_TIMEOUT = timedelta(hours=24)

DEFAULT_MIN_ADJUSTMENT = 1
DEFAULT_ADJUSTMENT_FACTOR = 0.33

DEBIT_NOTE_INTERVAL = "golem.com.scheme.payu.debit-note.interval-sec?"
PAYMENT_TIMEOUT = "golem.com.scheme.payu.payment-timeout-sec?"


class MidAgreementPaymentsNegotiator(ProposalNegotiator):
    def __init__(
        self,
        min_debit_note_interval: timedelta = DEFAULT_MIN_DEBIT_NOTE_INTERVAL,
        optimal_debit_note_interval: timedelta = DEFAULT_OPTIMAL_DEBIT_NOTE_INTERVAL,
        min_payment_timeout: timedelta = DEFAULT_MIN_PAYMENT_TIMEOUT,
        optimal_payment_timeout: timedelta = DEFAULT_OPTIMAL_PAYMENT_TIMEOUT,
        min_adjustment: int = DEFAULT_MIN_ADJUSTMENT,
        adjustment_factor: float = DEFAULT_ADJUSTMENT_FACTOR,
    ) -> None:
        self._min_debit_note_interval: int = int(min_debit_note_interval.total_seconds())
        self._optimal_debit_note_interval: int = int(optimal_debit_note_interval.total_seconds())
        self._min_payment_timeout: int = int(min_payment_timeout.total_seconds())
        self._optimal_payment_timeout: int = int(optimal_payment_timeout.total_seconds())
        self._min_adjustment = min_adjustment
        self._adjustment_factor = adjustment_factor

    async def __call__(self, demand_data: DemandData, proposal_data: ProposalData) -> None:
        offer_debit_note_interval = proposal_data.properties.get(DEBIT_NOTE_INTERVAL)
        offer_payment_timeout = proposal_data.properties.get(PAYMENT_TIMEOUT)
        if offer_debit_note_interval is None or offer_payment_timeout is None:
            raise RejectProposal("Offer doesn't support mid agreement payments")

        demand_debit_note_interval = demand_data.properties.get(DEBIT_NOTE_INTERVAL)
        demand_payment_timeout = demand_data.properties.get(PAYMENT_TIMEOUT)

        if (
            offer_debit_note_interval == demand_debit_note_interval
            and offer_payment_timeout == demand_payment_timeout
        ):
            logger.debug(
                "Mid agreement properties negotiation done with debit note interval: "
                f"{offer_debit_note_interval} and payment timeout: {offer_payment_timeout}"
            )
            return

        demand_data.properties[DEBIT_NOTE_INTERVAL] = self._calculate_new_value_proposition(
            offer_debit_note_interval,
            demand_debit_note_interval,
            self._min_debit_note_interval,
            self._optimal_debit_note_interval,
            proposal_data.state == "Initial",
        )
        demand_data.properties[PAYMENT_TIMEOUT] = self._calculate_new_value_proposition(
            offer_payment_timeout,
            demand_payment_timeout,
            self._min_payment_timeout,
            self._optimal_payment_timeout,
            proposal_data.state == "Initial",
        )
        logger.debug(
            "Ongoing mid agreement properties negotiation with"
            f" debit note interval: {demand_data.properties[DEBIT_NOTE_INTERVAL]}"
            f" and payment timeout: {demand_data.properties[PAYMENT_TIMEOUT]}"
        )
        return

    def _calculate_new_value_proposition(
        self,
        offered: int,
        previous: Optional[int],
        minimal: int,
        optimal: int,
        offer_is_initial: bool,
    ):
        # If this is the first proposal,
        # we request the maximum value, unless the offer is already higher.
        if previous is None or offer_is_initial:
            values = [offered, optimal]
            if previous is not None:
                values.append(previous)
            return max(values)
        # If we are offered a higher value, we accept it.
        elif offered >= previous:
            return offered
        # If our proposal was of our minimal value and there is still no consent,
        # we reject the offer.
        elif previous == minimal:
            raise RejectProposal("Offered mid agreement properties are too short")
        # In case of no consent, we adjust the proposed value closer to the offered one.
        else:
            new = previous - max(
                self._min_adjustment, math.ceil((previous - offered) * self._adjustment_factor)
            )
            return max(new, minimal, offered)
