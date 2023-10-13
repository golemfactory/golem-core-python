import logging
from dataclasses import dataclass
from typing import Optional

from golem.resources.proposal.proposal import ProposalData

logger = logging.getLogger(__name__)


@dataclass
class LinearCoeffs:
    price_storage_gib: float = 0.0
    price_mem_gib: float = 0.0
    price_cpu_sec: float = 0.0
    price_duration_sec: float = 0.0
    price_initial: float = 0.0

    @classmethod
    def from_proposal_data(cls, proposal_data: ProposalData) -> Optional["LinearCoeffs"]:
        pricing_model = proposal_data.properties.get("golem.com.pricing.model")

        if pricing_model != "linear":
            logger.debug(
                "Proposal `%s` is not in `linear` pricing model, ignoring",
                proposal_data.proposal_id,
            )
            return None

        coeffs = proposal_data.properties.get("golem.com.pricing.model.linear.coeffs")
        usage_vector = proposal_data.properties.get("golem.com.usage.vector")

        if not (
            isinstance(coeffs, (list, tuple))
            and isinstance(usage_vector, (list, tuple))
            and len(coeffs) == len(usage_vector) + 1
        ):
            logger.debug(
                "Proposal `%s` linear pricing coeffs must be a sequence"
                "matching a length of usage vector + 1, ignoring",
                proposal_data.proposal_id,
            )

            return None

        usage_vector_mapping = {
            # `_` versions are deprecated but still used by providers
            "golem.usage.cpu_sec": "price_cpu_sec",
            "golem.usage.cpu-sec": "price_cpu_sec",
            "golem.usage.duration_sec": "price_duration_sec",
            "golem.usage.duration-sec": "price_duration_sec",
            "golem.usage.storage_gib": "price_storage_gib",
            "golem.usage.storage-gib": "price_storage_gib",
            "golem.usage.gib": "price_mem_gib",
        }
        build_dict = {"price_initial": float(coeffs[-1])}

        for usage, coeff in zip(usage_vector, coeffs):
            key = usage_vector_mapping.get(usage)
            if key is None:
                continue
            build_dict[key] = float(coeff)

        return cls(**build_dict)
