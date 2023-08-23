from typing import Callable, List, Optional, Sequence, Tuple, Union

from golem.managers.base import ProposalScorer, ProposalScoringResult
from golem.resources import ProposalData

PropertyValueNumeric = Union[int, float]
BoundaryValues = Tuple[Tuple[float, PropertyValueNumeric], Tuple[float, PropertyValueNumeric]]


class MapScore(ProposalScorer):
    def __init__(
        self,
        callback: Callable[[ProposalData], Optional[float]],
        normalize: bool = False,
        normalize_flip: bool = False,
    ) -> None:
        self._callback = callback
        self._normalize = normalize
        self._normalize_flip = normalize_flip

    def __call__(self, proposals_data: Sequence[ProposalData]) -> ProposalScoringResult:
        result = [self._callback(proposal_data) for proposal_data in proposals_data]

        if not self._normalize or result is None:
            return result

        filtered = list(filter(None, result))
        if not filtered:
            return result

        result_max = max(filtered)
        result_min = min(filtered)
        result_div = result_max - result_min

        if result_div == 0:
            return result

        normalized_result: List[Optional[float]] = []
        for v in result:
            if v is not None:
                normalized_result.append((v - result_min) / result_div)
            else:
                normalized_result.append(v)

        if not self._normalize_flip:
            return normalized_result

        flipped_result: List[Optional[float]] = []
        for v in normalized_result:
            if v is not None:
                flipped_result.append(1 - v)
            else:
                flipped_result.append(v)
        return flipped_result
