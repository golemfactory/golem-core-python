from abc import ABC

from golem_core.demand_builder.model import Model


class BasePayload(Model, ABC):
    r"""Base class for descriptions of the payload required by the requestor.

    example usage::

        import asyncio

        from dataclasses import dataclass
        from golem_core.demand_builder.builder import DemandBuilder
        from golem_core.demand_builder.model import prop, constraint
        from golem_core.payload import BasePayload

        CUSTOM_RUNTIME_NAME = "my-runtime"
        CUSTOM_PROPERTY = "golem.srv.app.myprop"


        @dataclass
        class MyPayload(BasePayload):
            myprop: str = prop(CUSTOM_PROPERTY, default="myvalue")
            runtime: str = constraint("golem.runtime.name", default=CUSTOM_RUNTIME_NAME)
            min_mem_gib: float = constraint("golem.inf.mem.gib", ">=", default=16)
            min_storage_gib: float = constraint("golem.inf.storage.gib", ">=", default=1024)


        async def main():
            builder = DemandBuilder()
            payload = MyPayload(myprop="othervalue", min_mem_gib=32)
            await builder.add(payload)
            print(builder)

        asyncio.run(main())

    output::

        {'properties': {'golem.srv.app.myprop': 'othervalue'}, 'constraints': ['(&(golem.runtime.name=my-runtime)\n\t(golem.inf.mem.gib>=32)\n\t(golem.inf.storage.gib>=1024))']}
    """  # noqa: E501
