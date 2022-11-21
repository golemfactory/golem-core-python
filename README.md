# Golem Api Workshop

## Prereqs

* ubuntu + python3.8 (newer should also be fine) - maybe not necessary, but the library was not tested in any other environment
* git, poetry
* yagna 0.10.1 (PLEASE NOTE THE VERSION)

## Installation

```
git clone git@github.com:golemfactory/golem-api-python.git
cd golem-api-python
git checkout workshop
poetry install

#   Check if this works - wait for "SUCCESS" print
python3 workshop.py
```

##  API Reference

```
poetry run poe sphinx
firefox build/api.html
```

## Workshop

### Notes
*   All tasks should be solved by modyfying `workshop.py` file. Don't change `golem_api/*` or `workshop_internals.py`.
*   There are multiple correct solutions.
*   Be careful with Ctrl+C - we don't want to have too many providers with hanging activities on the devnet
    (or spawn your private `goth` subnet)

### Tasks

1.  Implement a blocklist.
    * Have a collection of provider ids.
    * Never sign agreements with those providers.
2.  Whenever a task fails, add the provider of the failing activity to the blocklist.
3.  Print some stats at the end of the execution, e.g.:
    *   number of batches per (activity/agreement/provider)
    *   average time/batch
    *   average time/batch for each provider
    *   ...
4.  Repeat failed tasks. 
    NOTE: Unless you have some clever idea I didn't think of, this will probably be done in two steps:
    *   Ensure all tasks are computed, accept that script hangs forever
    *   Ensure script stops after all tasks are computed
