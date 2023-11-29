import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, List, Optional

from ya_market import RequestorApi
from ya_market import models as models
from ya_market.exceptions import ApiException

from golem.resources.activity import Activity
from golem.resources.agreement.events import AgreementClosed, NewAgreement
from golem.resources.base import _NULL, Resource, api_call_wrapper
from golem.resources.invoice import Invoice

if TYPE_CHECKING:
    from golem.node import GolemNode
    from golem.resources.proposal import Proposal  # noqa


class Agreement(Resource[RequestorApi, models.Agreement, "Proposal", Activity, _NULL]):
    """A single agreement on the Golem Network.

    Sample usage::

        agreement = await proposal.create_agreement()
        await agreement.confirm()
        await agreement.wait_for_approval()
        activity = await agreement.create_activity()
        # Use the activity
        await agreement.terminate()
    """

    def __init__(self, node: "GolemNode", id_: str, data: Optional[models.Agreement] = None):
        super().__init__(node, id_, data)
        asyncio.create_task(node.event_bus.emit(NewAgreement(self)))

    @api_call_wrapper()
    async def confirm(self) -> None:
        """Confirm the agreement.

        First step that leads to an active agreement.
        """
        await self.api.confirm_agreement(self.id, app_session_id=self.node.app_session_id)

    @api_call_wrapper()
    async def wait_for_approval(self) -> bool:
        """Wait for provider's approval of the agreement.

        Second (and last) step leading to an active agreement.

        :returns: True if agreement was approved.
        """
        try:
            await self.api.wait_for_approval(self.id, timeout=15, _request_timeout=16)
            return True
        except ApiException as e:
            if e.status == 410:
                return False
            elif e.status == 408:
                #   TODO: maybe this should be in api_call_wrapper?
                return await self.wait_for_approval()
            else:
                raise

    @api_call_wrapper()
    async def create_activity(
        self, autoclose: bool = True, timeout: timedelta = timedelta(seconds=10)
    ) -> "Activity":
        """Create a new :any:`Activity` for this :any:`Agreement`.

        :param autoclose: Destroy the activity when the :any:`GolemNode` closes.
        :param timeout: Request timeout.
        """
        from golem.resources import Activity

        activity = await Activity.create(self.node, self.id, timeout)
        if autoclose:
            self.node.add_autoclose_resource(activity)
        self.add_child(activity)
        return activity

    @api_call_wrapper()
    async def terminate(self, reason: str = "") -> None:
        """Terminate the agreement.

        :param reason: Optional information for the provider explaining why the agreement was
            terminated.
        """
        try:
            await self.api.terminate_agreement(self.id, request_body={"message": reason})
            await self.node.event_bus.emit(AgreementClosed(self))
        except ApiException as e:
            if self._is_permanent_410(e):
                pass
            else:
                raise

    @property
    def invoice(self) -> Optional[Invoice]:
        """:any:`Invoice` for this :any:`Agreement`, or None if we didn't yet receive an invoice."""
        try:
            return [child for child in self.children if isinstance(child, Invoice)][0]
        except IndexError:
            return None

    @property
    def activities(self) -> List["Activity"]:
        """A list of :any:`Activity` created for this :any:`Agreement`."""
        from golem.resources.activity.resources import Activity  # circular imports prevention

        return [child for child in self.children if isinstance(child, Activity)]

    async def close_all(self) -> None:
        """Terminate agreement, destroy all activities.

        Ensure success -> retry if there are any problems.

        This is indended to be used in scenarios when we just want to end
        this agreement and we want to make sure it is really terminated (even if e.g. in some other
        separate task we're waiting for the provider to approve it).
        """
        #   TODO: This method is very ugly, also similar method could be useful for acivity only.
        #   BUT this probably should be a yagna-side change. Agreement.terminate() should
        #   just always succeed, as well as Activity.destroy() - yagna should repeat if necessary
        #   etc. We should only repeat in rare cases when we can't connect to our local `yagna`.
        #   Related issue: https://github.com/golemfactory/golem-core-python/issues/19

        #   Q: Why limit on repeats?
        #   A: So that we don't flood `yagna` with requests that will never succeed.
        #   Q: Why repeating 4 times?
        #   A: No particular reason.

        for i in range(1, 5):
            try:
                await self.terminate()
                break
            except ApiException as e:
                if self._is_permanent_410(e):
                    break
            await asyncio.sleep(2**i)

        for activity in self.activities:
            for i in range(1, 5):
                try:
                    await activity.destroy()
                    break
                except Exception:
                    pass
                await asyncio.sleep(2**i)

    @staticmethod
    def _is_permanent_410(e: ApiException) -> bool:
        #   TODO: Remove this check once https://github.com/golemfactory/yagna/issues/2264 is done
        #         and every 410 is permanent.
        if e.status != 410:
            return False
        return "from Approving" not in str(e) and "from Pending" not in str(e)

    @property
    def proposal(self) -> "Proposal":
        return self.parent
