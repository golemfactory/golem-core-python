from golem.exceptions import GolemException


class PayloadException(GolemException):
    pass


class ConstraintException(PayloadException):
    pass


class InvalidProperties(PayloadException):
    """`properties` given to `Payload.from_properties(cls, properties)` are invalid."""
