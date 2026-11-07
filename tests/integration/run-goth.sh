#!/bin/bash

# Capture host/daemon diagnostics; the goth network depends on docker state
# that is otherwise invisible from the pytest output.
_diag_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
[ -f "$_diag_dir/diagnostics.sh" ] && . "$_diag_dir/diagnostics.sh" && diag_run /tmp/goth-diagnostics-boot.txt

echo REMOVING OLD GOTH ENV CONFIG
rm /tmp/goth_interactive.env

echo CREATING VENV
rm -rf .envs/goth
python -m venv .envs/goth
source .envs/goth/bin/activate

echo INSTALLING TOOLS
.envs/goth/bin/python -m pip install --upgrade pip
.envs/goth/bin/python -m pip install --upgrade setuptools wheel

echo INSTALLING DEPENDENCIES
.envs/goth/bin/python -m pip install goth==0.17.0 pytest pytest-asyncio pexpect

echo CREATING ASSETS
.envs/goth/bin/python -m goth create-assets .envs/goth/assets
# disable use-proxy
sed -Ezi 's/("\n.*use\-proxy:\s)(True)/\1False/mg' .envs/goth/assets/goth-config.yml

echo STARTING NETWORK
cat .envs/goth/assets/goth-config.yml
.envs/goth/bin/python -m goth start .envs/goth/assets/goth-config.yml &
GOTH_PID=$!
echo $GOTH_PID

echo WAITING FOR NETWORK
STARTED_WAITING_AT=$((SECONDS + 900))
while [ ! -f /tmp/goth_interactive.env ]; do
  sleep 5
  if ! ps -p $GOTH_PID >/dev/null; then
    echo GOTH NETWORK FAILED TO START SUCESFULLY
    break
  fi
  if [ $SECONDS -gt $STARTED_WAITING_AT ]; then
    echo GOTH NETWORK FAILED TO START IN 15 MINUTES
    break
  fi
done

echo STARTUP COMPLETED
cat /tmp/goth_interactive.env

# Capture diagnostics again now that the network is running (container state,
# mounted yagna data and daemon configuration are only meaningful at this point).
diag_run /tmp/goth-diagnostics-network.txt 2>/dev/null || true
