import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar, Union

from golem.exceptions import GolemException
from golem.resources import (
    Activity,
    Agreement,
    Allocation,
    DemandData,
    Proposal,
    ProposalData,
    Script,
)
from golem.resources.activity import commands

logger = logging.getLogger(__name__)


class Batch:
    def __init__(self, activity) -> None:
        self._script = Script()
        self._activity = activity

    def deploy(self, deploy_args: Optional[commands.ArgsDict] = None):
        self._script.add_command(commands.Deploy(deploy_args))

    def start(self):
        self._script.add_command(commands.Start())

    def send_file(self, src_path: str, dst_path: str):
        self._script.add_command(commands.SendFile(src_path, dst_path))

    def download_file(self, src_path: str, dst_path: str):
        self._script.add_command(commands.DownloadFile(src_path, dst_path))

    def run(
        self,
        command: Union[str, List[str]],
        *,
        shell: Optional[bool] = None,
        shell_cmd: str = "/bin/sh",
    ):
        self._script.add_command(commands.Run(command, shell=shell, shell_cmd=shell_cmd))

    async def __call__(self):
        pooling_batch = await self._activity.execute_script(self._script)
        return await pooling_batch.wait()


class WorkContext:
    def __init__(self, activity: Activity):
        self._activity = activity

    async def deploy(
        self, deploy_args: Optional[commands.ArgsDict] = None, timeout: Optional[timedelta] = None
    ):
        pooling_batch = await self._activity.execute_commands(commands.Deploy(deploy_args))
        await pooling_batch.wait(timeout)

    async def start(self):
        pooling_batch = await self._activity.execute_commands(commands.Start())
        await pooling_batch.wait()

    async def terminate(self):
        await self._activity.destroy()

    async def run(
        self,
        command: Union[str, List[str]],
        *,
        shell: Optional[bool] = None,
        shell_cmd: str = "/bin/sh",
    ):
        return await self._activity.execute_commands(
            commands.Run(command, shell=shell, shell_cmd=shell_cmd)
        )

    async def create_batch(self) -> Batch:
        return Batch(self._activity)

    @property
    def activity(self) -> Activity:
        return self._activity

    async def get_provider_id(self):
        """Get the node id of the provider running this context."""
        return await self.activity.agreement.proposal.get_provider_id()

    async def get_provider_name(self):
        """Get the node name of the provider running this context."""
        return await self.activity.agreement.proposal.get_provider_name()


@dataclass
class WorkResult:
    result: Optional[Any] = None
    exception: Optional[Exception] = None
    extras: Dict = field(default_factory=dict)


WORK_PLUGIN_FIELD_NAME = "_work_plugins"

Work = Callable[[WorkContext], Awaitable[Optional[WorkResult]]]

DoWorkCallable = Callable[[Work], Awaitable[WorkResult]]


class ManagerEvent(ABC):
    pass


class ManagerException(GolemException):
    pass


class ManagerPluginException(ManagerException):
    pass


class Manager(ABC):
    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


TPlugin = TypeVar("TPlugin")


class NetworkManager(Manager, ABC):
    pass


class PaymentManager(Manager, ABC):
    @abstractmethod
    async def get_allocation(self) -> Allocation:
        ...


class DemandManager(Manager, ABC):
    @abstractmethod
    async def get_initial_proposal(self) -> Proposal:
        ...


class ProposalManager(Manager):
    @abstractmethod
    async def get_draft_proposal(self) -> Proposal:
        ...


class AgreementManager(Manager, ABC):
    @abstractmethod
    async def get_agreement(self) -> Agreement:
        ...


class ActivityManager(Manager, ABC):
    @abstractmethod
    async def get_activity(self) -> Activity:
        ...


class WorkManager(Manager, ABC):
    pass


class RejectProposal(ManagerPluginException):
    pass


class ProposalNegotiator(ABC):
    @abstractmethod
    def __call__(
        self, demand_data: DemandData, proposal_data: ProposalData
    ) -> Union[Awaitable[Optional[RejectProposal]], Optional[RejectProposal]]:
        ...


class ProposalManagerPlugin(ABC):
    _get_proposal: Callable[[], Awaitable[Proposal]]

    def set_proposal_callback(self, get_proposal: Callable[[], Awaitable[Proposal]]):
        self._get_proposal = get_proposal

    @abstractmethod
    async def get_proposal(self) -> Proposal:
        ...

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


ProposalScoringResult = Sequence[Optional[float]]


class ProposalScorer(ABC):
    @abstractmethod
    def __call__(
        self, proposals_data: Sequence[ProposalData]
    ) -> Union[Awaitable[ProposalScoringResult], ProposalScoringResult]:
        ...


ScorerWithOptionalWeight = Union[ProposalScorer, Tuple[float, ProposalScorer]]


class WorkManagerPlugin(ABC):
    @abstractmethod
    def __call__(self, do_work: DoWorkCallable) -> DoWorkCallable:
        ...


PricingCallable = Callable[[ProposalData], Optional[float]]
