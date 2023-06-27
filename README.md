# Golem Core

## Install

This project uses [Poetry](https://python-poetry.org/) for management, which needs to be installed to run following instructions.
Checkout the repository and run:

```bash
$ poetry install
```

## Examples

To run examples you need invoke them via poetry:

```bash
$ poetry run python examples/rate_providers/rate_providers.py
```

## CLI

```bash
$ python -m golem status

$ python -m golem find-node --runtime vm
$ python -m golem find-node --runtime vm --subnet public-beta 
$ python -m golem find-node --runtime vm --timeout 7  # stops after 7  seconds
$ python -m golem find-node --runtime vm --timeout 1m # stops after 60 seconds

$ python -m golem allocation list

$ python -m golem allocation new 1
$ python -m golem allocation new 2 --driver erc20 --network goerli

$ python -m golem allocation clean
```

## Docs

To build docs run following commands:

```bash
$ poetry run poe sphinx
```

Then you can open `build/api.html` file in your web browser. 

## Contributing

### Running code auto format

```bash
$ poetry run poe format
```

### Running code checks

```bash
$ poetry run poe checks
```

### Running tests

Unit tests:

```bash
$ poetry run poe tests_unit
```

Integration tests (requires running local `yagna` in requestor mode or `goth` in interactive mode):

```bash
$ poetry run poe tests_integration
```