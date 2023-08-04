import logging
from datetime import timedelta
from typing import Optional, Tuple

from golem.resources import ProposalData


class LinearAverageCostPricing:
    def __init__(self, average_cpu_load: float, average_duration: timedelta) -> None:
        self._average_cpu_load = average_cpu_load
        self._average_duration = average_duration

    def __call__(self, proposal_data: ProposalData) -> Optional[float]:
        coeffs = self._get_linear_coeffs(proposal_data)

        if coeffs is None:
            return None

        return self._calculate_cost(*coeffs)

    def _get_linear_coeffs(
        self, proposal_data: ProposalData
    ) -> Optional[Tuple[float, float, float]]:
        pricing_model = proposal_data.properties.get("golem.com.pricing.model")

        if pricing_model != "linear":
            logging.debug(
                f"Proposal `{proposal_data.proposal_id}` is not in `linear` pricing model, ignoring"
            )
            return None

        # TODO order of params golem.com.pricing.model.linear.coeffs order of params may vary
        coeffs = proposal_data.properties.get("golem.com.pricing.model.linear.coeffs")

        if not (isinstance(coeffs, (list, tuple)) and len(coeffs) == 3):
            logging.debug(
                f"Proposal `{proposal_data.proposal_id}` linear pricing coeffs must be a 3 element"
                "sequence, ignoring"
            )

            return None

        return tuple(float(c) for c in coeffs)  # type: ignore[return-value]

    def _calculate_cost(
        self, price_duration_sec: float, price_cpu_sec: float, price_initial: float
    ) -> float:
        average_duration_sec = self._average_duration.total_seconds()

        average_duration_cost = price_duration_sec * average_duration_sec
        average_cpu_cost = price_cpu_sec * self._average_cpu_load * average_duration_sec
        average_initial_price = price_initial / average_duration_sec

        return average_duration_cost + average_cpu_cost + average_initial_price
