#!/usr/bin/env bash

printf "*** STATUS ***\n"
python3 -m golem_core status

printf "\n*** FIND-NODE ***\n"
python3 -m golem_core find-node --runtime vm --timeout 1

printf "\n*** ALLOCATION LIST ***\n"
python3 -m golem_core allocation list

printf "\n*** ALLOCATION NEW ***\n"
python3 -m golem_core allocation new 1

printf "\n*** ALLOCATION NEW ***\n"
python3 -m golem_core allocation new 2 --driver erc20 --network rinkeby

printf "\n*** ALLOCATION LIST ***\n"
python3 -m golem_core allocation list

printf "\n*** ALLOCATION CLEAN ***\n"
python3 -m golem_core allocation clean

printf "\n*** ALLOCATION LIST ***\n"
python3 -m golem_core allocation list
