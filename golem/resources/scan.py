from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field


class ScanOfferEvent(BaseModel):
    """Represents a proposal (offer) from the market."""

    properties: Dict[str, Any] = Field(description="Provider capabilities and specifications")
    constraints: str = Field(description="Constraints expression")
    offerId: str = Field(description="Unique identifier for the offer")
    providerId: str = Field(description="provider node id")
    timestamp: datetime = Field(description="When event is received")
