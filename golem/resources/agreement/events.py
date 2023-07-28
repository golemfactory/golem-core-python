from typing import TYPE_CHECKING

from golem.resources.events import NewResource, ResourceClosed, ResourceDataChanged

if TYPE_CHECKING:
    from golem.resources.agreement.agreement import Agreement  # noqa


class NewAgreement(NewResource["Agreement"]):
    pass


class AgreementDataChanged(ResourceDataChanged["Agreement"]):
    pass


class AgreementClosed(ResourceClosed["Agreement"]):
    pass
