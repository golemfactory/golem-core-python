from typing import TYPE_CHECKING
from ya_activity import models

from .resource import Resource
from .resource_internals import ActivityApi, _NULL
from .market import Agreement

if TYPE_CHECKING:
    from golem_api import GolemNode


class Activity(Resource[ActivityApi, _NULL, Agreement, "Batch", _NULL]):
    @classmethod
    async def create(cls, node: "GolemNode", agreement_id: str) -> "Activity":
        api = cls._get_api(node)
        activity_id = await api.create_activity(agreement_id)
        return cls(node, activity_id)


class Batch(Resource[ActivityApi, _NULL, Activity, _NULL, models.RuntimeEvent]):
    pass
