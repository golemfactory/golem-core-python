#!/bin/bash

source /tmp/goth_interactive.env
YAGNA_PAYMENT_NETWORK=goerli pytest -sv tests/integration
