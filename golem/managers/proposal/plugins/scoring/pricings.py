import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from golem.payload import defaults
from golem.resources import LinearCoeffs, ProposalData

logger = logging.getLogger(__name__)


class LinearAverageCostPricing:
    def __init__(self, average_cpu_load: float, average_duration: timedelta) -> None:
        self._average_cpu_load = average_cpu_load
        self._average_duration = average_duration

    def __call__(self, proposal_data: ProposalData) -> Optional[float]:
        coeffs = LinearCoeffs.from_properties(proposal_data.properties)

        if coeffs is None:
            return None

        return self._calculate_cost(coeffs)

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"average_cpu_load={self._average_cpu_load}, "
            f"average_duration={self._average_duration})"
        )

    def _calculate_cost(self, coeffs: LinearCoeffs) -> float:
        average_duration_sec = Decimal(self._average_duration.total_seconds())

        average_initial_price = coeffs.price_initial
        average_duration_cost = coeffs.price_duration_sec * average_duration_sec
        average_cpu_cost = (
            coeffs.price_cpu_sec * Decimal(self._average_cpu_load) * average_duration_sec
        )

        return float(average_initial_price + average_duration_cost + average_cpu_cost)


class LinearPerCpuAverageCostPricing(LinearAverageCostPricing):
    def __call__(self, proposal_data: ProposalData) -> Optional[float]:
        coeffs = LinearCoeffs.from_properties(proposal_data.properties)
        cpu_count = proposal_data.properties.get(defaults.PROP_INF_CPU_THREADS)

        if coeffs is None or not cpu_count:
            return None

        cpu_count = Decimal(cpu_count)

        coeffs.price_initial /= cpu_count
        coeffs.price_duration_sec /= cpu_count

        return self._calculate_cost(coeffs)
