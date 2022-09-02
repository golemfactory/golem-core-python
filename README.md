# Yapapi refactoring

## Current state

First stage is ready.
Second stage starts.

## Start

### Install

```
poetry install
```

### Examples

1. `low_example.py` - example usage of the low-level interface
2. `mid_example.py` - POC of a mid-level interface
3. `cli_example.sh` - command line interface
4. `t/test_1.py` - few simple tests

### Docs

```
poetry run poe sphinx
firefox build/api.html
```

## Code

Important parts of the code:

* golem\_api/golem\_node.py - GolemNode, the only entrypoint
* golem\_api/low/resource.py - base class for all resources (defined as "any object in the Golem Network with an ID")
* golem\_api/low/market.py   - market API resources
* golem\_api/low/payment.py  - payment API resources
* golem\_api/low/exceptions.py  - exceptions raised from the `golem_api/low` code
* golem\_api/cli             - cli (imported in `golem_api/__main__`)
* golem\_api/low/yagna\_event\_collector.py - Class that processes `yagna` events

Parts that will be important in the future, but now they are far-from-ready drafts:

* golem\_api/mid            - POC of the mid-level interface
* golem\_api/events.py      - events emitted when something important happens
* golem\_api/event\_bus.py  - interface for emitting/receiving events
* golem\_api/low/api\_call\_wrapper.py - a wrapper for all API calls
* golem\_api/default\_logger.py - listens for events, prints them to a file

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

## NEXT STEPS

How I think we should continue with this project.
[NOTE: this section is obslete now, stages 1 + 2 are being more-or-less implemented now]

### 1. Implement necessary low-level objects and create a first "working" app

Current idea for the first app: capabilities similar to the current Task API.
Purpose:

* Ensure the low-level interface is good enough to write this sort of mid-level API
  in a convenient way
* Have some benchmark - e.g. it should not be slower then the current Task API
* It's good to have some E2E piece of code as early as possible

Details:

* Code should be universal - implementation of the next apps should require changing only app-specific code.
* "Happy path" is enough - we don't have to handle unusual/unexpected errors ...
* ... but we should know how they should be handled in the future

Rough estimate: 10 MD

### 2. Implement few more apps, as diverse as possible

Purpose: 
* Writing/modifying apps with golem\_api should be easy & fun. Here we try to find things that are not easy/fun
  and make them easier/more fun.
* We should try different "hard" things and ensure they are not that hard.
  + E.g. activity/agreement recycyling

App ideas:

* Service API compatibility POC 
  + We can run a service using the current Service class
  + We accept some things might not work
  + We don't have the Cluster/Network interface etc
  + (Bonus option: add a switch that turns off the "work generator" pattern)
* Verification-by-redundance POC
  + We have something like Task API, but with tasks repeated on different providers,
    task results from different providers are compared
* Collatz conjecture
  + Use as many activities as possible, with a simple cost limit (e.g. max estimated cost per hour)
* An app that requires two different demands
  + Purpose: ensure this is possible without much efforts
  + Could be something simple/stupid, no specific idea now

Details:

* App quality should match the quality of the first app (--> provious step)
* App code should be readable - without ugly hacks or weird patterns - developer should be able to understand
  how the app works and how to modify it. This is important.

Rough estimate: 2-3 MD per app.

### 3. Smoothen the edges. Implement "known" missing parts.

Details:

* Support for "expected" unhappy paths
* Missing parts of the negotiations
* Missing parts of the interface
* Network (just use the current `yapapi.network`? But this should be Resource?)
* ... (details after step 2)
* Maybe better docs?

Purpose: 

* Make it ready for internal tests. Ask Blue/Sieciech/Philip/etc to try it:
  + Best scenario: they conceive an app that is hard to write in this framework, and we know what needs changes
* Gather some feedback

Rough estimate: 3-10 MD

### 4. ...?

Business decision needed.

I see few different reasonable directions:

1. Public Alpha(Beta?)-quality release
2. More improvements, edge-smothing, going towards a "high quality" release
3. Don't push for the release, but start using internally. 
4. Create a first complete mainnet-production-grade app (cost management, reliability etc)
5. Provide full compatibility with the "old" high-level API
