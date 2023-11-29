from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from golem.payload import Constraints, Properties


@dataclass
class DemandData:
    properties: Properties
    constraints: Constraints
    demand_id: Optional[str]
    requestor_id: Optional[str]
    timestamp: datetime
