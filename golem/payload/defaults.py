from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from golem.payload.base import Payload, prop

RUNTIME_NAME = "golem.runtime.name"
RUNTIME_CAPABILITIES = "golem.runtime.capabilities"
INF_CPU_THREADS = "golem.inf.cpu.threads"
INF_MEM = "golem.inf.mem.gib"
INF_STORAGE = "golem.inf.storage.gib"


@dataclass
class NodeInfo(Payload):
    """Properties describing the information regarding the node."""

    name: Optional[str] = prop("golem.node.id.name", default=None)
    """human-readable name of the Golem node"""

    subnet_tag: Optional[str] = prop("golem.node.debug.subnet", default=None)
    """the name of the subnet within which the Demands and Offers are matched"""


@dataclass
class ActivityInfo(Payload):
    """Activity-related Properties."""

    cost_cap: Optional[Decimal] = prop("golem.activity.cost_cap", default=None)
    """Sets a Hard cap on total cost of the Activity (regardless of the usage vector or
    pricing function). The Provider is entitled to 'kill' an Activity which exceeds the
    capped cost amount indicated by Requestor.
    """

    cost_warning: Optional[Decimal] = prop("golem.activity.cost_warning", default=None)
    """Sets a Soft cap on total cost of the Activity (regardless of the usage vector or
    pricing function). When the cost_warning amount is reached for the Activity,
    the Provider is expected to send a Debit Note to the Requestor, indicating
    the current amount due
    """

    timeout_secs: Optional[float] = prop("golem.activity.timeout_secs", default=None)
    """A timeout value for batch computation (eg. used for container-based batch
    processes). This property allows to set the timeout to be applied by the Provider
    when running a batch computation: the Requestor expects the Activity to take
    no longer than the specified timeout value - which implies that
    eg. the golem.usage.duration_sec counter shall not exceed the specified
    timeout value.
    """

    expiration: Optional[datetime] = prop("golem.srv.comp.expiration", default=None)
    multi_activity: Optional[bool] = prop("golem.srv.caps.multi-activity", default=None)
    """Whether client supports multi_activity (executing more than one activity per agreement).
    """


@dataclass
class PaymentInfo(Payload):
    chosen_payment_platform: Optional[str] = prop("golem.com.payment.chosen-platform", default=None)
    """Payment platform selected to be used for this demand."""
