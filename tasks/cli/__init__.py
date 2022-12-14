from importlib import import_module, resources

import click
import psycopg2
from prettytable import PrettyTable

from tasks.run import run as _tasks_run
from .. import assets


@click.group()
def cli() -> None:
    pass

@cli.command()
@click.option("--dsn", type=str, default="")
def install(dsn) -> None:
    sql = resources.read_text(assets, 'install.sql')
    conn = psycopg2.connect(dsn)
    conn.cursor().execute(sql)

@cli.command()
@click.argument("module_name", type=str)
@click.option("--run-id", type=str, default=None)
@click.option("--dsn", type=str, default="")
@click.option("--workers", type=int, default=1)
def run(module_name, run_id, dsn, workers) -> None:
    module = import_module(module_name)
    _tasks_run(
        payload=module.PAYLOAD,
        get_tasks=module.get_tasks,
        results_cnt=module.results_cnt,
        run_id=run_id,
        dsn=dsn,
        workers=workers,
    )

@cli.command()
@click.option("--run-id", type=str, default=None)
@click.option("--dsn", type=str, default="")
def show(run_id, dsn):
    conn = psycopg2.connect(dsn)
    if run_id is None:
        run_id = _default_run_id(conn)
    if run_id is None:
        print("Database is empty")
        return

    data = _get_raw_data(conn, run_id)

    table = PrettyTable()
    table.field_names = [
        "ix", "activity_id", "status", "batches", "stop_reason"
    ]

    for row in data:
        table.add_row([str(x) for x in row])
    print(table.get_string())

@cli.command()
@click.option("--run-id", type=str, default=None)
@click.option("--dsn", type=str, default="")
def summary(run_id, dsn):
    conn = psycopg2.connect(dsn)
    if run_id is None:
        run_id = _default_run_id(conn)
    if run_id is None:
        print("Database is empty")
        return

    data = _get_raw_summary_data(conn, run_id)

    table = PrettyTable()
    table.field_names = [
        "run_id", "ready activities", "new activities", "other activities", "batches", "results"
    ]

    for row in data:
        table.add_row([str(x) for x in row])
    print(table.get_string())


def _default_run_id(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tasks.run ORDER BY created_ts DESC LIMIT 1")
    try:
        return cursor.fetchone()[0]
    except TypeError:
        return None


def _get_raw_data(conn, run_id):
    cursor = conn.cursor()
    cursor.execute(SHOW_DATA_SQL, {"app_session_id": run_id})
    return cursor.fetchall()

def _get_raw_summary_data(conn, run_id):
    cursor = conn.cursor()
    cursor.execute(SUMMARY_DATA_SQL, {"app_session_id": run_id})
    return cursor.fetchall()


SHOW_DATA_SQL = """
    WITH
    activities AS (
        SELECT  activity_id,
                count(DISTINCT batch_id) AS batch_cnt
        FROM    tasks.batches(%(app_session_id)s)
        GROUP BY 1
    )
    SELECT  row_number() OVER (ORDER BY all_act.created_ts),
            our_act.activity_id,
            all_act.status,
            our_act.batch_cnt,
            coalesce(all_act.stop_reason, '')
    FROM    activities      our_act
    JOIN    tasks.activity  all_act
       ON  all_act.id = our_act.activity_id
    ORDER BY all_act.created_ts
"""

SUMMARY_DATA_SQL = """
    WITH
    results AS (
        SELECT  cnt AS results_cnt
        FROM    tasks.results
        WHERE   run_id = %(app_session_id)s
        ORDER BY created_ts DESC LIMIT 1
    ),
    activity_batch_cnt AS (
        SELECT  activity_id,
                COUNT(DISTINCT batch_id)    AS batch_cnt
        FROM    tasks.batches(%(app_session_id)s)
        GROUP BY 1
    ),
    activity_batch_cnt_status AS (
        SELECT  SUM((a.status = 'READY')::int) AS ready_cnt,
                SUM((a.status = 'NEW')::int)   AS new_cnt,
                SUM((a.status NOT IN ('NEW', 'READY'))::int)   AS other_cnt,
                sum(b.batch_cnt)               AS batch_cnt
        FROM    tasks.activity      a
        JOIN    activity_batch_cnt  b
            ON  a.id = b.activity_id
    )
    SELECT  %(app_session_id)s AS run_id,
            coalesce(a.ready_cnt, 0),
            coalesce(a.new_cnt, 0),
            coalesce(a.other_cnt, 0),
            coalesce(a.batch_cnt, 0),
            r.results_cnt
    FROM    results r
    LEFT
    JOIN    activity_batch_cnt_status a
        ON  TRUE
"""
