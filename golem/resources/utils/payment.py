import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from golem.payload import defaults
from golem.resources.exceptions import PaymentValidationException
from golem.resources.utils.infrastructure import InfrastructureProps

logger = logging.getLogger(__name__)


ETH_EXPONENT = 10 ** Decimal(-18)


USAGE_VECTOR_TO_PRICE_MAPPING = {
    # `_` versions are deprecated but still used by providers
    "golem.usage.cpu_sec": "price_cpu_sec",
    "golem.usage.cpu-sec": "price_cpu_sec",
    "golem.usage.duration_sec": "price_duration_sec",
    "golem.usage.duration-sec": "price_duration_sec",
    "golem.usage.storage_gib": "price_storage_gib",
    "golem.usage.storage-gib": "price_storage_gib",
    "golem.usage.gib": "price_mem_gib",
}


@dataclass
class LinearCoeffs:
    usage_vector: List[str]
    price_storage_gib: Decimal = Decimal("0.0")
    price_mem_gib: Decimal = Decimal("0.0")
    price_cpu_sec: Decimal = Decimal("0.0")
    price_duration_sec: Decimal = Decimal("0.0")
    price_initial: Decimal = Decimal("0.0")

    def usage_vector_price(self) -> List[Decimal]:
        return [
            getattr(self, USAGE_VECTOR_TO_PRICE_MAPPING[vector])
            for vector in self.usage_vector
            if vector in USAGE_VECTOR_TO_PRICE_MAPPING
        ]

    @classmethod
    def from_properties(cls, properties: Dict) -> Optional["LinearCoeffs"]:
        pricing_model = properties.get(defaults.PROP_PRICING_MODEL)

        if pricing_model != "linear":
            logger.debug("Pricing model `%s` is not `linear`, ignoring", pricing_model)
            return None

        coeffs: List[Decimal] = [
            eth_decimal(coeff) for coeff in properties.get(defaults.PROP_PRICING_LINEAR_COEFFS, [])
        ]
        usage_vector: List[str] = [
            usage for usage in properties.get(defaults.PROP_USAGE_VECTOR, [])
        ]

        if len(coeffs) == 0 or len(coeffs) != len(usage_vector) + 1:
            logger.debug(
                "Linear pricing coeffs must be a sequence matching a length of usage vector + 1"
                "`%s` != `%s`, ignoring",
                len(coeffs),
                len(usage_vector) + 1,
            )

            return None
        build_dict: Dict[str, Any] = {"price_initial": coeffs[-1], "usage_vector": usage_vector}

        for usage, coeff in zip(usage_vector, coeffs):
            key = USAGE_VECTOR_TO_PRICE_MAPPING.get(usage)
            if key is None:
                continue
            build_dict[key] = coeff

        return cls(**build_dict)


class PayDocumentStatus(str, Enum):
    ISSUED = "ISSUED"
    RECEIVED = "RECEIVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


@dataclass
class PaymentProps:
    debit_notes_accept_timeout: Optional[int] = None
    """golem.com.payment.debit-notes.accept-timeout?"""
    debit_note_interval: Optional[int] = None
    """golem.com.scheme.payu.debit-note.interval-sec?"""
    payment_timeout: Optional[int] = None
    """golem.com.scheme.payu.payment-timeout-sec?"""

    @classmethod
    def from_properties(cls, properties: Dict) -> "PaymentProps":
        return cls(
            debit_notes_accept_timeout=properties.get(defaults.PROP_DEBIT_NOTES_ACCEPT_TIMEOUT),
            debit_note_interval=properties.get(defaults.PROP_DEBIT_NOTES_INTERVAL),
            payment_timeout=properties.get(defaults.PROP_PAYMENT_TIMEOUT),
        )


def eth_decimal(value: Union[str, Decimal]) -> Decimal:
    return Decimal(value).quantize(ETH_EXPONENT, ROUND_CEILING)


def validate_payment_max_cost(
    coeffs: LinearCoeffs,
    inf: InfrastructureProps,
    duration: timedelta,
    amount: Decimal,
    time_since_last_debit_note: Optional[timedelta] = None,
    amount_since_last_debit_note: Optional[Decimal] = None,
) -> Tuple[Decimal, Optional[Decimal]]:
    """Validate payment data max cost.

    Returns:
        maximum cost given `coeffs` and `infrastructure` could generate in
        - given `duration`
        - given `time_since_last_debit_note` if provided

    Raises: PaymentValidationException
    """
    max_cost = eth_decimal(
        coeffs.price_storage_gib * Decimal(inf.storage_gib)
        + coeffs.price_mem_gib * Decimal(inf.memory_gib)
        + coeffs.price_cpu_sec * Decimal(inf.cpu_threads) * Decimal(duration.total_seconds())
        + coeffs.price_duration_sec * Decimal(duration.total_seconds())
        + coeffs.price_initial
    )

    if amount > max_cost:
        raise PaymentValidationException(
            "Total amount due exceeds expected max possible cost " f"{amount} > {max_cost}"
        )

    if time_since_last_debit_note is None or amount_since_last_debit_note is None:
        return max_cost, None

    max_cost_since_last_debit_note = eth_decimal(
        coeffs.price_storage_gib * Decimal(inf.storage_gib)
        + coeffs.price_mem_gib * Decimal(inf.memory_gib)
        + coeffs.price_cpu_sec
        * Decimal(inf.cpu_threads)
        * Decimal(time_since_last_debit_note.total_seconds())
        + coeffs.price_duration_sec * Decimal(time_since_last_debit_note.total_seconds())
        + coeffs.price_initial
    )

    if amount_since_last_debit_note > max_cost_since_last_debit_note:
        raise PaymentValidationException(
            "Amount due since last debit note exceeds expected max possible cost "
            f"{amount_since_last_debit_note} > {max_cost_since_last_debit_note}"
        )

    return max_cost, max_cost_since_last_debit_note


def validate_payment_calculated_cost(
    coeffs: LinearCoeffs,
    amount: Decimal,
    usage_counter_vector: List,
    grace_amount: Decimal = 100 * ETH_EXPONENT,
) -> Decimal:
    """Validate payment amount calculated from vector usage.

    Returns: cost given `coeffs` and `usage_counter_vector` should generate

    Raises: PaymentValidationException
    """
    calculated_cost = coeffs.price_initial
    for price, value in zip(coeffs.usage_vector_price(), usage_counter_vector):
        calculated_cost += price * Decimal(value)
    calculated_cost = eth_decimal(calculated_cost)

    if amount > calculated_cost + grace_amount:
        raise PaymentValidationException(
            "Total amount due exceeds expected calculated cost " f"{amount} > {calculated_cost}"
        )

    return calculated_cost
