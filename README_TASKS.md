# TASKS - new approach to the task API

## What & why

### Main features

* Can work forever
* Cost per result management
* Budget management
* Execution monitoring in a pretty table
* Recovery in case of aburpt stop

### Current state

Works pretty well.
Interface is OK, although could be improved.
There is quite a lot that needs improvements, but current version should be good enough for a release, after some minor cleanup.

### Next steps

1.  Extract to a separate repo
2.  Decide on the final version of the interface
3.  (Maybe) fix some most important things, if we decide there are any (e.g. add typing?)
4.  Write a proper README
5.  Release

## Usage

### Prereqs

A running Postgresql server.

### Installation

Install `golem_core` and work from the repo directory.

### Commands

```
#   Install the database (creates schema "tasks")
python3 -m tasks install [--dsn]

#   Execute tasks
python3 -m tasks run my_module [--dsn, --run-id, --workers, --max-price, --budget]

#   Print a single-row summary table
python3 -m tasks summary [--dsn, --run-id]

#   Print a summary table with rows corresponding to activities
python3 -m tasks show [--dsn, --run-id]
```

#### Options
* `--dsn` - Database location, e.g. `dbname=go user=lem password=1234 host=localhost port=5432`, defaults to an empty string.
* `--run-id` - String, identifier of a run. Runs are totally separate. Defaults to a random string in the `run` command
               and to most recent `run-id` in `show` and `summary` commands.
               Repeated `run` with the same `run-id` will try to recover as much as possible from the previous execution
               (i.e. reuse activities and agreements).
* `--workers` - Integer, expected number of activities working at the same time. Defaults to 1.
* `--max-price` - Float, maximal cost per a single result. Details in a further section.
* `--budget` - String, how much we are willing to pay at most. Currently only accepted format is hourly budget, e.g. `3/h`. Defaults to `1/h`.


#### Sample run

```
python3 -m tasks run yacat --workers 10 --max-price 0.001 --budget 10/h --run-id test_1
```

### Utilities

```
# Constant monitoring of the current run
while true; do sleep 1; DATA=$(python3 -m tasks show); SUMMARY=$(python3 -m tasks summary); clear -x; echo "$DATA"; echo "$SUMMARY"; done
```

## APP Logic

### my\_module contents

Module should specify:

*   `PAYLOAD`
*   `get_tasks` - iterable yielding callables with arguments `(run_id, activity)`
*   `results_cnt` - function returning the number of computed results. This should be optional, but now is not.

In the future some optional things will be added (e.g. activity-preparing function, offer-scoring function).

Sample files: `yacat.py`, `example_tasks.py` (the latter doesn't work with restarting because `results_cnt` has no between-execution permanence).

### Restarting

```
#   Start
python3 -m tasks my_module run --workers 10 --run-id my_run

#   After a while kill the process in a non-graceful way (e.g. kill -9)
#   And start again
python3 -m tasks my_module run --workers 10 --run-id my_run
```
Second run will try to:

* reuse running activities, if it decides they are reusable
* reuse all agreements for non-reusable activities (i.e. will create new activities for the same agreements)

This will not work after Ctrl+C stop, because Ctrl+C terminates all agreements.
This is not super-useful now (as creating new activities is cheap), but might be more useful in the future.

### Budget

Whenever we receive a debit note, total amount for already accepted debit notes in the last hour is calculated.
We have a defined budget in a form `X/h`. If `calculated_amount + new_debit_note_amount > X`, program stops.

We create a new allocation for X each hour. This doesn't really matter now, but once
https://github.com/golemfactory/yagna/issues/2391 is done these two parts of logic will be cleanly merged into one 
(i.e. we won't be calculating any total budget, just trying to accept the invoice and stopping when this fails).

### Cost management

`--max-price=X` means that after some initial period (300s now) on every debit note we'll evaluate average cost of a single
result calculated by the activity and stop it if the cost exceedes X.

Note that now all debit notes/invoices are accepted, so our final price might be nowhere near the `--max-price` 
(e.g. we might get an invoice for 10 GLM after a second and we'll accept it if we have high enough budget).
