import asyncio
from typing import Any
from yapapi.payload import Payload as YapapiPayload, vm


class Payload(YapapiPayload):
    @staticmethod
    def from_image_hash(image_hash: str, **kwargs: Any) -> "Payload":
        """A non-async wrapper for `yapapi.vm.repo()` function.

        :param image_hash: Hash of the VM image.
        :param kwargs: Passed directly to `vm.repo()`.
        """
        loop = asyncio.new_event_loop()
        task = loop.create_task(vm.repo(image_hash=image_hash, **kwargs))
        result = loop.run_until_complete(task)
        loop.close()
        return result  # type: ignore
