#!/bin/bash

source /tmp/goth_interactive.env
YAGNA_PAYMENT_NETWORK=holesky pytest -sv tests/integration
