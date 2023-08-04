import asyncio
import random
from typing import Optional
from unittest.mock import AsyncMock

import pytest

from golem.managers import (
    BackgroundLoopMixin,
    DoWorkCallable,
    Manager,
    Work,
    WorkContext,
    WorkManager,
    WorkManagerPluginsMixin,
    WorkResult,
)


class FooBarBackgroundLoopManager(BackgroundLoopMixin, Manager):
    def __init__(self, foo: int, *args, **kwargs) -> None:
        self.foo: int = foo
        self.bar: Optional[int] = None

        super().__init__(*args, **kwargs)

    async def _background_loop(self) -> None:
        self.bar = self.foo
        while True:
            # await to switch out of the loop
            await asyncio.sleep(1)


async def test_background_loop_mixin_ok():
    given_bar = random.randint(0, 10)
    manager = FooBarBackgroundLoopManager(given_bar)
    assert not manager.is_started()
    assert manager.bar is None
    async with manager:
        # await to switch to `FooBarBackgroundLoopManager._background_loop`
        await asyncio.sleep(0.1)
        assert manager.is_started()
        assert manager.bar == given_bar
    assert not manager.is_started()
    assert manager.bar == given_bar


class FooBarWorkManagerPluginsManager(WorkManagerPluginsMixin, WorkManager):
    def __init__(self, do_work: DoWorkCallable, *args, **kwargs):
        self._do_work = do_work
        super().__init__(*args, **kwargs)

    async def do_work(self, work: Work) -> WorkResult:
        return await self._do_work_with_plugins(self._do_work, work)


@pytest.mark.parametrize(
    "expected_work_result, expected_called_count",
    (
        ("ZERO", None),
        ("ONE", 1),
        ("TWO", 2),
        ("TEN", 10),
    ),
)
async def test_work_manager_plugins_manager_mixin_ok(
    expected_work_result: str, expected_called_count: Optional[int]
):
    async def _do_work_func(work: Work) -> WorkResult:
        work_result = await work(AsyncMock())
        if not isinstance(work_result, WorkResult):
            work_result = WorkResult(result=work_result)
        return work_result

    async def _work(context: WorkContext) -> Optional[WorkResult]:
        return WorkResult(result=expected_work_result)

    def _plugin(do_work: DoWorkCallable) -> DoWorkCallable:
        async def wrapper(work: Work) -> WorkResult:
            work_result = await do_work(work)
            work_result.extras["called_count"] = work_result.extras.get("called_count", 0) + 1
            return work_result

        return wrapper

    work_plugins = [_plugin for _ in range(expected_called_count or 0)]

    manager = FooBarWorkManagerPluginsManager(do_work=_do_work_func, plugins=work_plugins)

    result = await manager.do_work(_work)

    assert result.result == expected_work_result
    assert result.extras.get("called_count") == expected_called_count
