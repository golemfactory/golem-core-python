import asyncio
import random
from typing import Optional

from golem.managers import BackgroundLoopMixin, Manager


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
