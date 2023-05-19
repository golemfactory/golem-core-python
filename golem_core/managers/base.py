from abc import ABC, abstractmethod
from typing import Awaitable, Callable, List, Optional


class Batch:
    def deploy(self):
        ...

    def start(self):
        ...

    def terminate(self):
        ...

    def run(self, command: str):
        ...

    async def __call__(self):
        ...


class WorkContext:
    async def deploy(self):
        ...

    async def start(self):
        ...

    async def terminate(self):
        ...

    async def run(self, command: str):
        ...

    async def create_batch(self) -> Batch:
        ...


class WorkResult:
    ...


WorkDecorator = Callable[["DoWorkCallable"], "DoWorkCallable"]


class Work(ABC):
    _work_decorators: Optional[List[WorkDecorator]]

    def __call__(self, context: WorkContext) -> Optional[WorkResult]:
        ...


DoWorkCallable = Callable[[Work], Awaitable[WorkResult]]


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
