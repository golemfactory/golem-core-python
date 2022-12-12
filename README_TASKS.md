## Install

```
$ python3 -m tasks install --dsn=""
```

## Execute

```
#   New run
$ python3 -m tasks run python_module

#   This will try to resume run "my_run_id"
$ python3 -m tasks run --run-id my_run_id python_module
```

## Monitoring

```
#   Last run_id
$ python3 -m tasks show

#   Specific run_id
$ python3 -m tasks show --run-id my_run_id

#   Auto-updating table
$ while true; do sleep 1; DATA=$(python3 -m tasks show); clear -x; echo "$DATA"; done
```
