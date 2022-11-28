from importlib import import_module, resources

import click

from tasks.run import run as _tasks_run
from .. import assets


@click.group()
def cli() -> None:
    pass

@cli.command()
def install() -> None:
    print(resources.read_text(assets, 'install.sql'))

@cli.command()
@click.argument("module_name", type=str)
def run(module_name) -> None:
    module = import_module(module_name)
    _tasks_run(module.PAYLOAD, module.get_tasks, module.results_cnt)
