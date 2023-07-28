from golem.managers.work.mixins import WorkManagerPluginsMixin
from golem.managers.work.plugins import redundancy_cancel_others_on_first_done, retry, work_plugin
from golem.managers.work.queue import QueueWorkManager
from golem.managers.work.sequential import SequentialWorkManager

__all__ = (
    "QueueWorkManager",
    "WorkManagerPluginsMixin",
    "SequentialWorkManager",
    "work_plugin",
    "redundancy_cancel_others_on_first_done",
    "retry",
)
