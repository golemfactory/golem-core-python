from golem_core.core.market_api.exceptions import BaseMarketApiException


class BaseDemandOfferBaseException(BaseMarketApiException):
    pass


class ConstraintException(BaseDemandOfferBaseException):
    pass


class InvalidPropertiesError(BaseDemandOfferBaseException):
    """`properties` given to `DemandOfferBaseModel.from_properties(cls, properties)` are invalid."""
