#!/bin/bash

source /tmp/goth_interactive.env
YAGNA_PAYMENT_NETWORK=rinkeby pytest -sv tests/integration
