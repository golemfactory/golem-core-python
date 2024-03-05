from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from golem.payload.properties import Properties

AgreementId = str


@dataclass
class AgreementData:
    agreement_id: AgreementId
    provider_id: Optional[str]
    approved_date: Optional[datetime]
    properties: Properties
    agreement_duration: Optional[timedelta]
