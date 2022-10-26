# Golem Api

## Current state

Few apps are in a "pretty advanced POC" state:

*   blender - just like the `yapapi` blender
*   verification by redundance
*   yacat-with-business-logic ("Run as many tasks as possible but ensure they cost at most X per result")

## Start

### Install

```
poetry install
```

### Docs

```
poetry run poe sphinx
firefox build/api.html
```

### Examples

1. `low_example.py`         - few low-level interface examples
2. `mid_example.py`         - a mid-level interface example
3. `cli_example.sh`         - command line interface example
4. `blender.py`
5. `redundace.py`           - verification by redundance example
6. `yacat.py`               - yacat with business logic
7. `detached_activity.py`   - create activity, print activity\_id, stop (but keep the activity running)
8. `attach.py`              - take an activity\_id and start using it


## CLI

```bash
python3 -m golem_api status

python3 -m golem_api find-node --runtime vm
python3 -m golem_api find-node --runtime vm --subnet public-beta 
python3 -m golem_api find-node --runtime vm --timeout 7  # stops after 7  seconds
python3 -m golem_api find-node --runtime vm --timeout 1m # stops after 60 seconds

python3 -m golem_api allocation list

python3 -m golem_api allocation new 1
python3 -m golem_api allocation new 2 --driver erc20 --network rinkeby

python3 -m golem_api allocation clean
```

"Status" command is not really useful now, but we don't yet have components to make it good.
