from golem_core.core.market_api.exceptions import BaseMarketApiException


class BaseDemandOfferBaseException(BaseMarketApiException):
    pass


class ConstraintException(BaseDemandOfferBaseException):
    pass


class InvalidPropertiesError(BaseDemandOfferBaseException):
    """Raised by `DemandOfferBaseModel.from_properties(cls, properties)` when given invalid `properties`."""
