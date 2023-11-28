from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from golem.payload import Constraints, Properties

ProposalId = str

# TODO: Use Enum
ProposalState = Literal["Initial", "Draft", "Rejected", "Accepted", "Expired"]


@dataclass
class ProposalData:
    properties: Properties
    constraints: Constraints
    proposal_id: Optional[ProposalId]
    issuer_id: Optional[str]
    state: ProposalState
    timestamp: datetime
    prev_proposal_id: Optional[str]
