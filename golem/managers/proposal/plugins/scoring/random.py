from random import random
from typing import Sequence, Tuple, Union

from golem.managers.base import ProposalScoringResult, Scorer
from golem.resources import ProposalData

PropertyValueNumeric = Union[int, float]
BoundaryValues = Tuple[Tuple[float, PropertyValueNumeric], Tuple[float, PropertyValueNumeric]]


class RandomScore(Scorer):
    def __call__(self, proposals_data: Sequence[ProposalData]) -> ProposalScoringResult:
        return [random() for _ in range(len(proposals_data))]
