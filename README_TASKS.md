## Install

Running Postgresql is required.

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

## Logic

### Payments 

Budget is defined by the `--budget` switch. Currently only accepted option is budget per hour (--budget=7/h).
Every debit note/invoice is accepted. Execution stops when a debit note can't be accepted because we exceeded the limit.

### Cost management

### Restart & recovery
