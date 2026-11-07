#!/bin/bash

# Collect diagnostics when the test run finishes, regardless of outcome.
_diag_dir="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$_diag_dir/diagnostics.sh" ]; then
  . "$_diag_dir/diagnostics.sh"
  trap 'diag_run /tmp/goth-diagnostics-final.txt 2>/dev/null || true' EXIT
fi

source /tmp/goth_interactive.env
YAGNA_PAYMENT_NETWORK=holesky pytest -sv tests/integration
