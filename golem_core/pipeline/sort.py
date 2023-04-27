import asyncio
import heapq
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import AsyncIterator, Awaitable, Callable, Generic, List, Optional, Tuple, TypeVar

TElement = TypeVar("TElement")


@dataclass(order=True)
class ScoredElement(Generic[TElement]):
    score: float
    element: TElement = field(compare=False)


class Sort:
    """Re-orders elements using a provided scoring function."""

    _no_more_elements: bool = False

    def __init__(
        self,
        score_function: Callable[[TElement], Awaitable[Optional[float]]],
        min_elements: Optional[int] = None,
        max_wait: Optional[timedelta] = None,
        min_wait: Optional[timedelta] = None,
    ):
        """Init Sort.

        :param score_function: Element-scoring function. Higher score -> better element.
            Score `None` indicates an unacceptable element - it will be ignored by the Sort.
        :param min_elements: If not None, :func:`__call__` will not yield anything until
            Sort gathers at least that many elements with a non-None score (but `max_wait` overrides
            this).
        :param max_wait: If not None, we'll not wait for `min_elements` longer than that.
        :param min_wait: If not None, we'll wait for at least that.
        """
        self._score_function = score_function
        self._min_elements = min_elements
        self._max_wait = max_wait
        self._min_wait = min_wait

        self._scored_elements: List[ScoredElement] = []

    async def __call__(self, elements: AsyncIterator[TElement]) -> AsyncIterator[TElement]:
        """Consumes incoming elements as fast as possible. Always yields a element with the \
        highest score.

        :param elements: Stream of element to be reordered.
            In fact, this could be stream of whatever, as long as this whatever matches
            the scoring function, and this whatever would be yielded (TODO - maybe turn this into a
            general Sort?
            https://github.com/golemfactory/golem-core-python/issues/11).
        """
        self._no_more_elements = False
        element_scorer_task = asyncio.get_event_loop().create_task(self._process_stream(elements))
        try:
            element: TElement
            async for element, score in self._elements():
                print(f"Yielding element with score {-1 * score}")
                yield element
        except asyncio.CancelledError:
            element_scorer_task.cancel()
            self._no_more_elements = True

    async def _elements(self) -> AsyncIterator[Tuple[TElement, float]]:
        await self._wait_until_ready()

        while self._scored_elements or not self._no_more_elements:
            try:
                scored_element = heapq.heappop(self._scored_elements)
                yield scored_element.element, scored_element.score
            except IndexError:
                await asyncio.sleep(0.1)

    async def score_function(self, element: TElement) -> Optional[float]:
        return await self._score_function(element)

    async def _process_stream(self, element_stream: AsyncIterator[TElement]) -> None:
        async for element in element_stream:
            #   TODO: https://github.com/golemfactory/golem-core-python/issues/37
            score = await self.score_function(element)
            if score is None:
                continue

            score = score * -1  # heap -> smallest values first -> reverse
            heapq.heappush(self._scored_elements, ScoredElement(score, element))
        self._no_more_elements = True

    async def _wait_until_ready(self) -> None:
        start = datetime.now()

        while True:
            await asyncio.sleep(0.1)
            now = datetime.now()
            if self._min_wait is not None and now - start < self._min_wait:
                # force wait until time exceeds `min_wait`
                continue
            if self._min_elements is None or len(self._scored_elements) >= self._min_elements:
                break
            if self._max_wait is not None and now - start >= self._max_wait:
                break
