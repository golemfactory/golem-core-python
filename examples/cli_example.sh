#!/usr/bin/env bash

printf "*** STATUS ***\n"
python3 -m golem status

printf "\n*** FIND-NODE ***\n"
python3 -m golem find-node --runtime vm --timeout 1

printf "\n*** ALLOCATION LIST ***\n"
python3 -m golem allocation list

printf "\n*** ALLOCATION NEW ***\n"
python3 -m golem allocation new 1

printf "\n*** ALLOCATION NEW ***\n"
python3 -m golem allocation new 2 --driver erc20 --network goerli

printf "\n*** ALLOCATION LIST ***\n"
python3 -m golem allocation list

printf "\n*** ALLOCATION CLEAN ***\n"
python3 -m golem allocation clean

printf "\n*** ALLOCATION LIST ***\n"
python3 -m golem allocation list
