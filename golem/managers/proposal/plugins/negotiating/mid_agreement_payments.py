import logging
from datetime import timedelta
from typing import Optional

from golem.managers.base import ProposalNegotiator, RejectProposal
from golem.resources import DemandData, ProposalData

logger = logging.getLogger(__name__)

DEFAULT_MIN_DEBIT_NOTE_INTERVAL = timedelta(minutes=1)
DEFAULT_REQUESTED_DEBIT_NOTE_INTERVAL = timedelta(minutes=10)
DEFAULT_MIN_PAYMENT_TIMEOUT = timedelta(minutes=2)
DEFAULT_REQUESTED_PAYMENT_TIMEOUT = timedelta(hours=24)

DEFAULT_MIN_ADJUSTMENT = 1
DEFAULT_ADJUSTMENT_FACTOR = 3

DEBIT_NOTE_INTERVAL = "golem.com.scheme.payu.debit-note.interval-sec?"
PAYMENT_TIMEOUT = "golem.com.scheme.payu.payment-timeout-sec?"


class MidAgreementPaymentsNegotiator(ProposalNegotiator):
    def __init__(
        self,
        min_debit_note_interval: timedelta = DEFAULT_MIN_DEBIT_NOTE_INTERVAL,
        requested_debit_note_interval: timedelta = DEFAULT_REQUESTED_DEBIT_NOTE_INTERVAL,
        min_payment_timeout: timedelta = DEFAULT_MIN_PAYMENT_TIMEOUT,
        requested_payment_timeout: timedelta = DEFAULT_REQUESTED_PAYMENT_TIMEOUT,
        min_adjustment: int = DEFAULT_MIN_ADJUSTMENT,
        adjustment_factor: int = DEFAULT_ADJUSTMENT_FACTOR,
    ) -> None:
        self._min_debit_note_interval: int = int(min_debit_note_interval.total_seconds())
        self._requested_debit_note_interval: int = int(
            requested_debit_note_interval.total_seconds()
        )
        self._min_payment_timeout: int = int(min_payment_timeout.total_seconds())
        self._requested_payment_timeout: int = int(requested_payment_timeout.total_seconds())
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
                f"{offer_debit_note_interval} and  payment timeout: {offer_payment_timeout}"
            )
            return

        demand_data.properties[DEBIT_NOTE_INTERVAL] = self._calculate_new_value_proposition(
            offer_debit_note_interval,
            demand_debit_note_interval,
            self._min_debit_note_interval,
            self._requested_debit_note_interval,
        )
        demand_data.properties[PAYMENT_TIMEOUT] = self._calculate_new_value_proposition(
            offer_payment_timeout,
            demand_payment_timeout,
            self._min_payment_timeout,
            self._requested_payment_timeout,
        )
        logger.debug(
            "Ongoing mid agreement properties negotiation with"
            f" debit note interval: {demand_data.properties[DEBIT_NOTE_INTERVAL]}"
            f" and payment timeout: {demand_data.properties[PAYMENT_TIMEOUT]}"
        )
        return

    def _calculate_new_value_proposition(
        self, offered: int, previous: Optional[int], minimal: int, requested: int
    ):
        # If this is a first proposition we propose maximum value
        if previous is None:
            return max(offered, requested)
        # If we are offered a bigger value we accept it
        elif offered >= previous:
            return offered
        # If our proposal was of our minimal value and there is still no consent we reject the offer
        elif previous == minimal:
            raise RejectProposal("Offered mid agreement properties are too short")
        # In case of no consent we lower propose value closer to offered value
        else:
            new = previous - max(
                self._min_adjustment, (previous - offered) // self._adjustment_factor
            )
            return max(new, minimal, offered)
