import logging
from typing import Optional

from golem.resources import LinearCoeffs, ProposalData
from golem.utils.logging import trace_span

logger = logging.getLogger(__name__)


class LinearCoeffsCost:
    def __init__(self, coeff_name: str) -> None:
        self._coeff_name = coeff_name

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(coeff_name={self._coeff_name})"

    @trace_span(lambda s: str(s), show_results=True)
    def __call__(self, proposal_data: ProposalData) -> Optional[float]:
        coeffs = LinearCoeffs.from_proposal_data(proposal_data)

        if coeffs is None:
            return None

        return getattr(coeffs, self._coeff_name)
