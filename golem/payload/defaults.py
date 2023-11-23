from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from os import getenv
from typing import Optional, Tuple

from golem.payload.base import Payload, constraint, prop
from golem.payload.constraints import Constraints
from golem.payload.properties import Properties

RUNTIME_NAME = "golem.runtime.name"
RUNTIME_CAPABILITIES = "golem.runtime.capabilities"
INF_CPU_THREADS = "golem.inf.cpu.threads"
INF_MEM = "golem.inf.mem.gib"
INF_STORAGE = "golem.inf.storage.gib"

DEFAULT_PAYMENT_DRIVER: str = getenv("YAGNA_PAYMENT_DRIVER", "erc20").lower()
DEFAULT_PAYMENT_NETWORK: str = getenv("YAGNA_PAYMENT_NETWORK", "goerli").lower()

DEFAULT_LIFETIME = timedelta(minutes=30)
DEFAULT_SUBNET: str = getenv("YAGNA_SUBNET", "public")


@dataclass
class NodeInfo(Payload):
    """Properties and constraints describing the information regarding the node."""

    name: Optional[str] = prop("golem.node.id.name", default=None)
    """human-readable name of the Golem node"""

    subnet_tag: Optional[str] = prop("golem.node.debug.subnet", default=DEFAULT_SUBNET)
    _subnet_tag_constraint: Optional[str] = constraint(
        "golem.node.debug.subnet", default=None, init=False
    )
    """the name of the subnet within which the Demands and Offers are matched"""

    def __post_init__(self):
        self._subnet_tag_constraint = self.subnet_tag


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
    """The datetime until which any started activities will last."""

    lifetime: Optional[timedelta] = field(default=None)
    """Lifetime of the activities from the moment the demand is placed.

    Convenience property, used only in case the actual `expiration` is not provided.
    """

    multi_activity: Optional[bool] = prop("golem.srv.caps.multi-activity", default=None)
    """Whether client supports multi_activity (executing more than one activity per agreement).
    """

    def __post_init__(self):
        if self.expiration and self.lifetime:
            raise ValueError(
                "Ambiguous definition - either the expiration or the lifetime must be provided."
            )

        # in case the expiration itself is not provided, set the default lifetime instead
        # so that the expiration can be dynamically constructed when needed
        if not self.expiration and not self.lifetime:
            self.lifetime = DEFAULT_LIFETIME

    async def build_properties_and_constraints(self) -> Tuple[Properties, Constraints]:
        # we don't want to freeze the expiration, so we're making a copy here
        if not self.expiration:
            activity_info = replace(self)
            assert activity_info.lifetime  # set in `__post_init__`
            activity_info.expiration = datetime.now(timezone.utc) + activity_info.lifetime
            return await activity_info.build_properties_and_constraints()

        return await super().build_properties_and_constraints()


@dataclass
class PaymentInfo(Payload):
    chosen_payment_platform: Optional[str] = prop("golem.com.payment.chosen-platform", default=None)
    """Payment platform selected to be used for this demand."""

    debit_notes_accept_timeout: int = prop(
        "golem.com.payment.debit-notes.accept-timeout?", default=120
    )
