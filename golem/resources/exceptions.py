from typing import TYPE_CHECKING

from golem.exceptions import GolemException

if TYPE_CHECKING:
    from golem.resources.base import Resource


class ResourceException(GolemException):
    pass


class ResourceNotFound(ResourceException):
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
