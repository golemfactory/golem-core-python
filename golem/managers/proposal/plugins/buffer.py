import logging
from datetime import timedelta
from typing import Callable, Optional

from golem.managers import ProposalManagerPlugin
from golem.resources import Proposal
from golem.utils.asyncio.buffer import BackgroundFillBuffer, Buffer, ExpirableBuffer, SimpleBuffer
from golem.utils.asyncio.tasks import resolve_maybe_awaitable
from golem.utils.logging import trace_span
from golem.utils.typing import MaybeAwaitable

logger = logging.getLogger(__name__)


class BufferPlugin(ProposalManagerPlugin):
    def __init__(
        self,
        min_size: int,
        max_size: int,
        fill_concurrency_size=1,
        fill_at_start=False,
        get_expiration_func: Optional[
            Callable[[Proposal], MaybeAwaitable[Optional[timedelta]]]
        ] = None,
        on_expiration_func: Optional[Callable[[Proposal], MaybeAwaitable[None]]] = None,
    ) -> None:
        self._min_size = min_size
        self._max_size = max_size
        self._fill_concurrency_size = fill_concurrency_size
        self._fill_at_start = fill_at_start
        self._get_expiration_func = get_expiration_func
        self._on_expiration_func = on_expiration_func

        buffer: Buffer[Proposal] = SimpleBuffer()

        if self._get_expiration_func is not None:
            buffer = ExpirableBuffer(
                buffer=buffer,
                get_expiration_func=self._get_expiration_func,
                on_expired_func=self._on_item_expire,
            )

        self._buffer: BackgroundFillBuffer[Proposal] = BackgroundFillBuffer(
            buffer=buffer,
            fill_func=self._call_feed_func,
            fill_concurrency_size=self._fill_concurrency_size,
            on_added_func=self._on_item_added,
        )

    async def _call_feed_func(self) -> Proposal:
        return await self._get_proposal()

    async def _on_item_added(self, item: Proposal) -> None:
        count_current = self._buffer.size()
        count_with_requested = self._buffer.size_with_requested()
        pending = count_with_requested - count_current

        logger.debug(
            "Item added, having %d items, and %d pending, target %d",
            count_current,
            pending,
            self._max_size,
        )

    async def _on_item_expire(self, item: Proposal):
        logger.debug("Item %r expired, rejecting proposal and requesting fill", item)
        await item.reject("Proposal no longer needed")
        await self._request_items()

        if self._on_expiration_func is not None:
            await resolve_maybe_awaitable(self._on_expiration_func, item)

    @trace_span()
    async def start(self) -> None:
        await self._buffer.start()

        if self._fill_at_start:
            await self._request_items()

    @trace_span()
    async def stop(self) -> None:
        await self._buffer.stop()

    async def _request_items(self) -> None:
        count_current = self._buffer.size()
        count_with_requested = self._buffer.size_with_requested()
        requested = self._max_size - count_with_requested

        logger.debug(
            "Having %d items, and %d already requested, requesting additional %d items to match"
            " target %d",
            count_current,
            count_with_requested - count_current,
            requested,
            self._max_size,
        )

        await self._buffer.request(requested)

    @trace_span(show_results=True)
    async def get_proposal(self) -> Proposal:
        if not self._get_items_count():
            logger.debug("No items to get, requesting fill")
            await self._request_items()

        proposal = await self._get_item()

        items_count = self._get_items_count()
        if items_count < self._min_size:
            logger.debug(
                "Items count is now `%s` which is below min size `%d`, requesting fill",
                items_count,
                self._min_size,
            )
            await self._request_items()
        else:
            logger.debug(
                "Target items is now `%s` which is not below min size `%d`, requesting fill not"
                " needed",
                items_count,
                self._min_size,
            )

        return proposal

    async def _get_item(self) -> Proposal:
        return await self._buffer.get()

    def _get_items_count(self) -> int:
        return self._buffer.size()
