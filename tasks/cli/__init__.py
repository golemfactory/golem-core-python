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
@click.option("--max-price", type=float)
def run(module_name, run_id, dsn, workers, max_price) -> None:
    module = import_module(module_name)
    _tasks_run(
        payload=module.PAYLOAD,
        get_tasks=module.get_tasks,
        results_cnt=module.results_cnt,
        run_id=run_id,
        dsn=dsn,
        workers=workers,
        result_max_price=max_price,
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
        "ix", "activity_id", "status", "batches", "GLM", "GLM/result", "results", "stop_reason"
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
        "run_id", "ready activities", "new activities", "other activities", "batches", "GLM", "GLM/result", "results"
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
    cursor.execute(SHOW_DATA_SQL, {"run_id": run_id})
    return cursor.fetchall()

def _get_raw_summary_data(conn, run_id):
    cursor = conn.cursor()
    cursor.execute(SUMMARY_DATA_SQL, {"run_id": run_id})
    return cursor.fetchall()


SHOW_DATA_SQL = """
    WITH
    activities AS (
        WITH activity_batch AS (
            SELECT  activity_id,
                    count(DISTINCT batch_id) AS batch_cnt
            FROM    tasks.batches(%(run_id)s)
            GROUP BY 1
        ),
        activity_total_amount AS (
            SELECT  f.activity_id,
                    max(t.amount) AS total_amount
            FROM    tasks.debit_notes(%(run_id)s) f
            JOIN    tasks.debit_note t
                ON  f.debit_note_id = t.id
            GROUP BY 1
        )
        SELECT  coalesce(b.activity_id, d.activity_id) AS activity_id,
                coalesce(b.batch_cnt, 0)               AS batch_cnt,
                coalesce(d.total_amount, 0)            AS total_amount
        FROM    activity_batch          b
        FULL
        OUTER
        JOIN    activity_total_amount   d
            ON  b.activity_id = d.activity_id
    ),
    batch_result_ratio AS (
        WITH
        results AS (
            SELECT  cnt
            FROM    tasks.results
            WHERE   run_id = %(run_id)s
            ORDER BY created_ts DESC
            LIMIT 1
        ),
        batches AS (
            SELECT  sum(batch_cnt) AS cnt
            FROM    activities
        )
        SELECT  results.cnt / batches.cnt AS batch_result_ratio
        FROM    batches, results
    )
    SELECT  row_number() OVER (ORDER BY all_act.created_ts),
            our_act.activity_id,
            all_act.status,
            our_act.batch_cnt,
            round(our_act.total_amount, 6),
            CASE WHEN our_act.batch_cnt > 0 AND brr.batch_result_ratio > 0
                THEN round(our_act.total_amount / (our_act.batch_cnt * brr.batch_result_ratio), 6)::text
                ELSE ''::text
            END,
            round(our_act.batch_cnt * brr.batch_result_ratio, 2),
            coalesce(all_act.stop_reason, '')
    FROM    activities      our_act
    JOIN    tasks.activity  all_act
       ON   all_act.id = our_act.activity_id
    JOIN    batch_result_ratio brr
        ON  TRUE
    ORDER BY all_act.created_ts
"""

SUMMARY_DATA_SQL = """
    WITH
    results AS (
        SELECT  cnt AS results_cnt
        FROM    tasks.results
        WHERE   run_id = %(run_id)s
        ORDER BY created_ts DESC
        LIMIT 1
    ),
    activity_batch_cnt AS (
        SELECT  activity_id,
                COUNT(DISTINCT batch_id)    AS batch_cnt
        FROM    tasks.batches(%(run_id)s)
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
    ),
    total_amount AS (
        WITH activity_amount AS (
            SELECT  f.activity_id,
                    max(t.amount) AS amount
            FROM    tasks.debit_notes(%(run_id)s) f
            JOIN    tasks.debit_note              t
                ON  f.debit_note_id = t.id
            GROUP BY 1
        )
        SELECT  sum(amount)   AS amount
        FROM    activity_amount
    )
    SELECT  %(run_id)s AS run_id,
            coalesce(a.ready_cnt, 0),
            coalesce(a.new_cnt, 0),
            coalesce(a.other_cnt, 0),
            coalesce(a.batch_cnt, 0),
            round(coalesce(ta.amount, 0), 6),
            CASE WHEN r.results_cnt > 0
                THEN round(coalesce(ta.amount, 0) / r.results_cnt, 6)::text
                ELSE ''::text
            END,
            r.results_cnt
    FROM    results r
    LEFT
    JOIN    activity_batch_cnt_status a
        ON  TRUE
    LEFT
    JOIN    total_amount ta
        ON TRUE
"""
