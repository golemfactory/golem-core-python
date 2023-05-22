from abc import ABC

from golem_core.core.market_api.resources.demand.demand_offer_base.model import DemandOfferBaseModel


class Payload(DemandOfferBaseModel, ABC):
    r"""Base class for descriptions of the payload required by the requestor.

    example usage::

        import asyncio

        from dataclasses import dataclass
        from golem_core.core.market_api import DemandBuilder, prop, constraint, Payload, RUNTIME_NAME, INF_MEM, INF_STORAGE

        CUSTOM_RUNTIME_NAME = "my-runtime"
        CUSTOM_PROPERTY = "golem.srv.app.myprop"


        @dataclass
        class MyPayload(Payload):
            myprop: str = prop(CUSTOM_PROPERTY, default="myvalue")
            runtime: str = constraint(RUNTIME_NAME, default=CUSTOM_RUNTIME_NAME)
            min_mem_gib: float = constraint(INF_MEM, ">=", default=16)
            min_storage_gib: float = constraint(INF_STORAGE, ">=", default=1024)


        async def main():
            builder = DemandBuilder()
            payload = MyPayload(myprop="othervalue", min_mem_gib=32)
            await builder.add(payload)
            print(builder)

        asyncio.run(main())

    output::

        {'properties': {'golem.srv.app.myprop': 'othervalue'}, 'constraints': ['(&(golem.runtime.name=my-runtime)\n\t(golem.inf.mem.gib>=32)\n\t(golem.inf.storage.gib>=1024))']}
    """  # noqa: E501

    def __hash__(self) -> int:
        return hash((str(self._serialize_properties()), self._serialize_constraints()))
