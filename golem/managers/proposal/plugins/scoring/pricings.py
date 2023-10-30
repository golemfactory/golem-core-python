import logging
from datetime import timedelta
from typing import Optional

from golem.resources import LinearCoeffs, ProposalData

logger = logging.getLogger(__name__)


class LinearAverageCostPricing:
    def __init__(self, average_cpu_load: float, average_duration: timedelta) -> None:
        self._average_cpu_load = average_cpu_load
        self._average_duration = average_duration

    def __call__(self, proposal_data: ProposalData) -> Optional[float]:
        coeffs = LinearCoeffs.from_proposal_data(proposal_data)

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
        average_duration_sec = self._average_duration.total_seconds()

        average_duration_cost = coeffs.price_duration_sec * average_duration_sec
        average_cpu_cost = coeffs.price_cpu_sec * self._average_cpu_load * average_duration_sec
        average_initial_price = coeffs.price_initial / average_duration_sec

        return average_duration_cost + average_cpu_cost + average_initial_price
