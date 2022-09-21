import asyncio
from typing import Any
from yapapi.payload import Payload as YapapiPayload, vm


class Payload(YapapiPayload):
    @staticmethod
    def from_image_hash(image_hash: str, **kwargs: Any) -> "Payload":
        """There's no reason for vm.repo to be async, and a sync version is more convenient"""
        loop = asyncio.new_event_loop()
        task = loop.create_task(vm.repo(image_hash=image_hash, **kwargs))
        result = loop.run_until_complete(task)
        loop.close()
        return result  # type: ignore
