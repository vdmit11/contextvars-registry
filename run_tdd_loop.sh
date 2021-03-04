#!/usr/bin/env sh

until find . \( ! -regex '.*/\..*' \) -name '*.py' | entr -d ./run_tests.sh; do sleep 1; done
