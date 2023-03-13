#!/bin/bash

echo REMOVING OLD GOTH ENV CONFIG
rm /tmp/goth_interactive.env

echo CREATING VENV
rm -rf .envs/goth
python -m venv .envs/goth
source .envs/goth/bin/activate

echo INSTALLING TOOLS
.envs/goth/bin/python -m pip install --upgrade pip
.envs/goth/bin/python -m pip install --upgrade setuptools wheel

echo ISNTALLING DEPENDENCIES
.envs/goth/bin/python -m pip install goth pytest pytest-asyncio pexpect

echo CREATING ASSETS
.envs/goth/bin/python -m goth create-assets .envs/goth/assets
# disable use-proxy
sed -Ezi 's/("\n.*use\-proxy:\s)(True)/\1False/mg' .envs/goth/assets/goth-config.yml

echo STARTING NETWORK
.envs/goth/bin/python -m goth start .envs/goth/assets/goth-config.yml &
GOTH_PID=$!
echo $GOTH_PID

echo WAITING FOR NETWORK
while [ ! -f /tmp/goth_interactive.env ]; do
  sleep 1
  if ! ps -p $GOTH_PID >/dev/null; then
    echo GOTH NETWORK FAILED TO START SUCESFULLY
    break
  fi
done

echo STARTUP COMPLETED
cat /tmp/goth_interactive.env
