from importlib import import_module

import click

from tasks.run import run as _tasks_run


@click.group()
def cli() -> None:
    pass

@cli.command()
def install() -> None:
    print("INSTALL")

@cli.command()
@click.argument("module_name", type=str)
def run(module_name) -> None:
    module = import_module(module_name)
    _tasks_run(module.PAYLOAD, module.get_tasks, module.results_cnt)
