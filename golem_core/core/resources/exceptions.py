from typing import TYPE_CHECKING

from golem_core.core.exceptions import BaseCoreException

if TYPE_CHECKING:
    from golem_core.core.resources.base import Resource

class BaseResourceException(BaseCoreException):
    pass


class MissingConfiguration(BaseResourceException):
    def __init__(self, key: str, description: str):
        self._key = key
        self._description = description

    def __str__(self) -> str:
        return f"Missing configuration for {self._description}. Please set env var {self._key}."


class ResourceNotFound(BaseResourceException):
    """Raised on an attempt to interact with a resource that doesn't exist.

    Example::

        async with GolemNode() as golem:
            agreement_id = "".join(["a" for x in range(64)])
            agreement = golem.agreement(agreement_id)
            try:
                await agreement.get_data()
            except ResourceNotFound as e:
                print(f"Agreement with id {e.resource.id} doesn't exist")


        """
    def __init__(self, resource: "Resource"):
        self._resource = resource

        msg = f"{resource} doesn't exist"
        super().__init__(msg)

    @property
    def resource(self) -> "Resource":
        """Resource that caused the exception."""
        return self._resource
