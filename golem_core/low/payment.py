from datetime import datetime, timedelta, timezone
from typing import List, Tuple, TYPE_CHECKING, Union
from decimal import Decimal

from ya_payment import RequestorApi, models

from golem_core.events import ResourceClosed
from .exceptions import NoMatchingAccount
from .api_call_wrapper import api_call_wrapper
from .resource import Resource
from .resource_internals import _NULL

if TYPE_CHECKING:
    from golem_core.golem_node import GolemNode
    from .activity import Activity
    from .market import Agreement


class Allocation(Resource[RequestorApi, models.Allocation, _NULL, _NULL, _NULL]):
    """A single allocation on the Golem Network.

    Created with one of the :class:`Allocation`-returning methods of the :any:`GolemNode`.
    """
    @api_call_wrapper(ignore=[404, 410])
    async def release(self) -> None:
        """Release the allocation.

        Remaining amount will be available again. This is the final operation -
        released allocation is not available anymore.
        """
        await self.api.release_allocation(self.id)
        self.node.event_bus.emit(ResourceClosed(self))

    @classmethod
    async def create_any_account(
        cls, node: "GolemNode", amount: Decimal, network: str, driver: str,
    ) -> "Allocation":
        for account in await cls._get_api(node).get_requestor_accounts():
            if (
                account.driver.lower() == driver.lower()
                and account.network.lower() == network.lower()
            ):
                break
        else:
            raise NoMatchingAccount(network, driver)

        return await cls.create_with_account(node, account, amount)

    @classmethod
    async def create_with_account(
        cls,
        node: "GolemNode",
        account: models.Account,
        amount: Decimal,
    ) -> "Allocation":
        timestamp = datetime.now(timezone.utc)
        timeout = timestamp + timedelta(days=365 * 10)

        data = models.Allocation(
            address=account.address,
            payment_platform=account.platform,
            total_amount=str(amount),
            timestamp=timestamp,
            timeout=timeout,

            #   This will probably be removed one day (consent-related thing)
            make_deposit=False,

            #   We must set this here because of the ya_client interface
            allocation_id="",
            spent_amount="",
            remaining_amount="",
        )

        return await cls.create(node, data)

    @classmethod
    async def create(cls, node: "GolemNode", data: models.Allocation) -> "Allocation":
        api = cls._get_api(node)
        created = await api.create_allocation(data)
        return cls(node, created.allocation_id, created)

    @api_call_wrapper()
    async def demand_properties_constraints(self) -> Tuple[List[models.MarketProperty], List[str]]:
        data = await self.api.get_demand_decorations([self.id])
        return data.properties, data.constraints


class DebitNote(Resource[RequestorApi, models.DebitNote, "Activity", _NULL, _NULL]):
    """A single debit note on the Golem Network.

    Ususally created by a :any:`GolemNode` initialized with `collect_payment_events = True`.
    """
    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full debit note amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).total_amount_due
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper()
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(total_amount_accepted=str(amount), allocation_id=allocation.id)
        await self.api.accept_debit_note(self.id, acceptance)


class Invoice(Resource[RequestorApi, models.Invoice, "Agreement", _NULL, _NULL]):
    """A single invoice on the Golem Network.

    Ususally created by a :any:`GolemNode` initialized with `collect_payment_events = True`."""
    async def accept_full(self, allocation: Allocation) -> None:
        """Accept full invoice amount using a given :any:`Allocation`."""
        amount_str = (await self.get_data()).amount
        await self.accept(allocation, Decimal(amount_str))

    @api_call_wrapper()
    async def accept(self, allocation: Allocation, amount: Union[Decimal, float]) -> None:
        acceptance = models.Acceptance(total_amount_accepted=str(amount), allocation_id=allocation.id)
        await self.api.accept_invoice(self.id, acceptance)
