from importlib import import_module, resources

import click
import psycopg2

from tasks.run import run as _tasks_run
from .. import assets


@click.group()
def cli() -> None:
    pass

@cli.command()
@click.option("--dsn", default="")
def install(dsn) -> None:
    sql = resources.read_text(assets, 'install.sql')
    conn = psycopg2.connect(dsn)
    conn.cursor().execute(sql)

@cli.command()
@click.argument("module_name", type=str)
@click.option("--dsn", default="")
def run(module_name, dsn) -> None:
    module = import_module(module_name)
    _tasks_run(
        payload=module.PAYLOAD,
        get_tasks=module.get_tasks,
        results_cnt=module.results_cnt,
        dsn=dsn,
    )
