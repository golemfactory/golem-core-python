from abc import ABC

from golem_core.demand_builder.model import ComputingResourceModel


class Payload(ComputingResourceModel, ABC):
    r"""Base class for descriptions of the payload required by the requestor.

    example usage::

        import asyncio

        from dataclasses import dataclass
        from golem_core.demand_builder import props
        from golem_core.demand_builder.builder import DemandBuilder
        from golem_core.demand_builder.model import prop, constraint
        from golem_core.payload import Payload

        CUSTOM_RUNTIME_NAME = "my-runtime"
        CUSTOM_PROPERTY = "golem.srv.app.myprop"


        @dataclass
        class MyPayload(Payload):
            myprop: str = prop(CUSTOM_PROPERTY, default="myvalue")
            runtime: str = constraint(props.RUNTIME_NAME, default=CUSTOM_RUNTIME_NAME)
            min_mem_gib: float = constraint(props.INF_MEM, ">=", default=16)
            min_storage_gib: float = constraint(props.INF_STORAGE, ">=", default=1024)


        async def main():
            builder = DemandBuilder()
            payload = MyPayload(myprop="othervalue", min_mem_gib=32)
            await builder.add(payload)
            print(builder)

        asyncio.run(main())

    output::

        {'properties': {'golem.srv.app.myprop': 'othervalue'}, 'constraints': ['(&(golem.runtime.name=my-runtime)\n\t(golem.inf.mem.gib>=32)\n\t(golem.inf.storage.gib>=1024))']}
    """  # noqa: E501
