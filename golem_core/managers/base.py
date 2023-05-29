from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from golem_core.core.activity_api import Activity, Script, commands
from golem_core.core.events import Event


class Batch:
    def __init__(self, activity) -> None:
        self._script = Script()
        self._activity = activity

    def deploy(self):
        self._script.add_command(commands.Deploy())

    def start(self):
        self._script.add_command(commands.Start())

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

    async def deploy(self):
        pooling_batch = await self._activity.execute_commands(commands.Deploy())
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
    extras: Optional[Dict] = None


WorkDecorator = Callable[["DoWorkCallable"], "DoWorkCallable"]


class Work(ABC):
    _work_decorators: Optional[List[WorkDecorator]]

    def __call__(self, context: WorkContext) -> Awaitable[Optional[WorkResult]]:
        ...


DoWorkCallable = Callable[[Work], Awaitable[WorkResult]]


class ManagerEvent(Event, ABC):
    pass


class Manager(ABC):
    ...


class PaymentManager(Manager, ABC):
    @abstractmethod
    async def get_allocation(self) -> "Allocation":
        ...


class NegotiationManager(Manager, ABC):
    @abstractmethod
    async def get_offer(self) -> "Offer":
        ...


class OfferManager(Manager, ABC):
    @abstractmethod
    async def get_offer(self) -> "Offer":
        ...


class AgreementManager(Manager, ABC):
    @abstractmethod
    async def get_agreement(self) -> "Agreement":
        ...


class ActivityManager(Manager, ABC):
    @abstractmethod
    async def get_activity(self) -> "Activity":
        ...

    @abstractmethod
    async def do_work(self, work: Work) -> WorkResult:
        ...


class WorkManager(Manager, ABC):
    ...
