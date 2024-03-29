import asyncio
from typing import Optional

import click

from golem.cli.utils import (
    CliPayload,
    async_golem_wrapper,
    format_allocations,
    format_demands,
    format_proposals,
    parse_timedelta_str,
)
from golem.node import GolemNode
from golem.payload.defaults import DEFAULT_PAYMENT_DRIVER, DEFAULT_PAYMENT_NETWORK, DEFAULT_SUBNET


@click.group()
def cli() -> None:
    pass


@cli.group()
def allocation() -> None:
    pass


@allocation.command("list")
@async_golem_wrapper
async def allocation_list(golem: GolemNode) -> None:
    allocations = await golem.allocations()
    click.echo(format_allocations(allocations))


@allocation.command("new")
@click.argument("amount", type=float)
@click.option("--network", type=str, default=DEFAULT_PAYMENT_NETWORK)
@click.option("--driver", type=str, default=DEFAULT_PAYMENT_DRIVER)
@async_golem_wrapper
async def allocation_new(
    golem: GolemNode,
    amount: float,
    network: str,
    driver: str,
) -> None:
    allocation = await golem.create_allocation(
        amount,
        network=network,
        driver=driver,
        autoclose=False,
    )
    click.echo(format_allocations([allocation]))


@allocation.command("clean")
@async_golem_wrapper
async def allocation_clean(golem: GolemNode) -> None:
    for allocation in await golem.allocations():
        await allocation.release()
        click.echo(allocation.id)


@cli.command()
@async_golem_wrapper
async def status(golem: GolemNode) -> None:
    allocations = await golem.allocations()
    demands = await golem.demands()
    msg_parts = [
        "ALLOCATIONS",
        format_allocations(allocations),
        "",
        "DEMANDS",
        format_demands(demands),
    ]
    click.echo("\n".join(msg_parts))


@cli.command()
@click.option("--runtime", type=str, required=True)
@click.option("--subnet", type=str, default=DEFAULT_SUBNET)
@click.option("--timeout", "timeout_str", type=str, required=False)
@async_golem_wrapper
async def find_node(
    golem: GolemNode, runtime: str, subnet: str, timeout_str: Optional[str]
) -> None:
    timeout = parse_timedelta_str(timeout_str) if timeout_str is not None else None
    cnt = 0

    async def get_nodes() -> None:
        nonlocal cnt

        payload = CliPayload(runtime)
        demand = await golem.create_demand(payload, subnet=subnet)

        async for proposal in demand.initial_proposals():
            click.echo(format_proposals([proposal], cnt == 0))
            cnt += 1

    try:
        await asyncio.wait_for(get_nodes(), timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        print(f"{cnt} proposals found")
