from random import random
from typing import Callable, List, Optional, Sequence, Tuple, Union

from golem.managers.base import ManagerPluginException, ManagerScorePlugin, ProposalPluginResult
from golem.payload.constraints import PropertyName
from golem.resources import ProposalData

PropertyValueNumeric = Union[int, float]
BoundaryValues = Tuple[Tuple[float, PropertyValueNumeric], Tuple[float, PropertyValueNumeric]]


class PropertyValueLerpScore(ManagerScorePlugin):
    def __init__(
        self,
        property_name: PropertyName,
        *,
        minus_one_at: Optional[PropertyValueNumeric] = None,
        zero_at: Optional[PropertyValueNumeric] = None,
        one_at: Optional[PropertyValueNumeric] = None,
        raise_on_missing=False,
        raise_on_bad_value=False,
    ) -> None:
        self._property_name = property_name
        self._boundary_values = self._get_boundary_values(minus_one_at, zero_at, one_at)
        self._raise_on_missing = raise_on_missing
        self._raise_on_bad_value = raise_on_bad_value

    def __call__(self, proposals_data: Sequence[ProposalData]) -> ProposalPluginResult:
        return [self._calculate_linear_score(proposal_data) for proposal_data in proposals_data]

    def _calculate_linear_score(self, proposal_data: ProposalData) -> Optional[float]:
        property_value = self._get_property_value(proposal_data)

        if property_value is None:
            return None

        bounds_min = min([self._boundary_values[0][1], self._boundary_values[1][1]])
        bounds_max = max([self._boundary_values[0][1], self._boundary_values[1][1]])

        x1, y1 = self._boundary_values[0]
        x2, y2 = self._boundary_values[1]
        y3 = min(bounds_max, max(property_value, bounds_min))

        # formula taken from https://www.johndcook.com/interpolatorhelp.html
        return (((y2 - y3) * x1) + ((y3 - y1) * x2)) / (y2 - y1)

    def _get_property_value(self, proposal_data: ProposalData) -> Optional[PropertyValueNumeric]:
        try:
            property_value = proposal_data.properties[self._property_name]
        except KeyError:
            if self._raise_on_missing:
                raise ManagerPluginException(f"Property `{self._property_name}` is not found!")

            return None

        if not isinstance(property_value, (int, float)):
            if self._raise_on_bad_value:
                raise ManagerPluginException(
                    f"Field `{self._property_name}` value type must be an `int` or `float`!"
                )

            return None

        return property_value

    def _get_boundary_values(
        self,
        minus_one_at: Optional[PropertyValueNumeric] = None,
        zero_at: Optional[PropertyValueNumeric] = None,
        one_at: Optional[PropertyValueNumeric] = None,
    ) -> BoundaryValues:
        if minus_one_at is not None:
            bounds_min = (-1, minus_one_at)
        elif zero_at is not None:
            bounds_min = (0, zero_at)
        else:
            raise ManagerPluginException(
                "One of boundary arguments `minus_one_at`, `zero_at` must be provided!"
            )

        if one_at is not None:
            bounds_max = (1, one_at)
        elif zero_at is not None:
            bounds_max = (0, zero_at)
        else:
            raise ManagerPluginException(
                "One of boundary arguments `zero_at`, `one_at` must be provided!"
            )

        return bounds_min, bounds_max


class RandomScore(ManagerScorePlugin):
    def __call__(self, proposals_data: Sequence[ProposalData]) -> ProposalPluginResult:
        return [random() for _ in range(len(proposals_data))]


class MapScore(ManagerScorePlugin):
    def __init__(
        self,
        callback: Callable[[ProposalData], Optional[float]],
        normalize: bool = False,
        normalize_flip: bool = False,
    ) -> None:
        self._callback = callback
        self._normalize = normalize
        self._normalize_flip = normalize_flip

    def __call__(self, proposals_data: Sequence[ProposalData]) -> ProposalPluginResult:
        result = [self._callback(proposal_data) for proposal_data in proposals_data]

        if not self._normalize or result is None:
            return result

        filtered = filter(None, result)
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
