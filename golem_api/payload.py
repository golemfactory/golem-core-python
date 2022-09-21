import asyncio
from yapapi.payload import Payload, vm


def sync_vm_repo(image_hash: str, **kwargs):
    """There's no reason for vm.repo to be async, and a sync version is more convenient"""
    loop = asyncio.new_event_loop()
    task = loop.create_task(vm.repo(image_hash=image_hash, **kwargs))
    result = loop.run_until_complete(task)
    loop.close()
    return result


Payload.from_image_hash = sync_vm_repo
