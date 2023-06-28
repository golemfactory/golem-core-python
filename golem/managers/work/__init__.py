from golem.managers.work.plugins import redundancy_cancel_others_on_first_done, retry, work_plugin
from golem.managers.work.sequential import SequentialWorkManager

__all__ = (
    "SequentialWorkManager",
    "work_plugin",
    "redundancy_cancel_others_on_first_done",
    "retry",
)
