from golem.managers.base import ManagerEvent
from golem.resources import Agreement, ResourceEvent


class AgreementReleased(ManagerEvent, ResourceEvent[Agreement]):
    pass
