from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

from golem.exceptions import GolemException
from golem.resources import (
    Activity,
    Agreement,
    Allocation,
    DemandData,
    Proposal,
    ProposalData,
    ResourceEvent,
    Script,
)
from golem.resources.activity import commands
from golem.utils.logging import trace_span


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

    async def deploy(self, deploy_args: Optional[commands.ArgsDict] = None):
        pooling_batch = await self._activity.execute_commands(commands.Deploy(deploy_args))
        await pooling_batch.wait()

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


@dataclass
class WorkResult:
    result: Optional[Any] = None
    exception: Optional[Exception] = None
    extras: Dict = field(default_factory=dict)


WORK_PLUGIN_FIELD_NAME = "_work_plugins"


class Work(ABC):
    _work_plugins: Optional[List["WorkManagerPlugin"]]

    def __call__(self, context: WorkContext) -> Awaitable[Optional[WorkResult]]:
        ...


DoWorkCallable = Callable[[Work], Awaitable[WorkResult]]


class ManagerEvent(ResourceEvent, ABC):
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

    async def start(self):
        ...

    async def stop(self):
        ...


TPlugin = TypeVar("TPlugin")


class ManagerPluginsMixin(Generic[TPlugin]):
    def __init__(self, plugins: Optional[Sequence[TPlugin]] = None, *args, **kwargs) -> None:
        self._plugins: List[TPlugin] = list(plugins) if plugins is not None else []

        super().__init__(*args, **kwargs)

    @trace_span()
    def register_plugin(self, plugin: TPlugin):
        self._plugins.append(plugin)

    @trace_span()
    def unregister_plugin(self, plugin: TPlugin):
        self._plugins.remove(plugin)


class NetworkManager(Manager, ABC):
    ...


class PaymentManager(Manager, ABC):
    @abstractmethod
    async def get_allocation(self) -> Allocation:
        ...


class DemandManager(Manager, ABC):
    @abstractmethod
    async def get_initial_proposal(self) -> Proposal:
        ...


class NegotiationManager(Manager, ABC):
    @abstractmethod
    async def get_draft_proposal(self) -> Proposal:
        ...


class AgreementManager(Manager, ABC):
    @abstractmethod
    async def get_agreement(self) -> Agreement:
        ...


class ActivityManager(Manager, ABC):
    @abstractmethod
    async def do_work(self, work: Work) -> WorkResult:
        ...


class WorkManager(Manager, ABC):
    ...


class RejectProposal(ManagerPluginException):
    pass


class NegotiationManagerPlugin(ABC):
    @abstractmethod
    def __call__(
        self, demand_data: DemandData, proposal_data: ProposalData
    ) -> Union[Awaitable[Optional[RejectProposal]], Optional[RejectProposal]]:
        ...


ProposalPluginResult = Sequence[Optional[float]]


class ManagerScorePlugin(ABC):
    @abstractmethod
    def __call__(
        self, proposals_data: Sequence[ProposalData]
    ) -> Union[Awaitable[ProposalPluginResult], ProposalPluginResult]:
        ...


ManagerPluginWithOptionalWeight = Union[ManagerScorePlugin, Tuple[float, ManagerScorePlugin]]


class WorkManagerPlugin(ABC):
    def __call__(self, do_work: DoWorkCallable) -> DoWorkCallable:
        ...


PricingCallable = Callable[[ProposalData], Optional[float]]
