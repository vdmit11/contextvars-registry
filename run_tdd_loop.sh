#!/usr/bin/env sh

until find . \( ! -regex '.*/\..*' \) \( -name '*.py' -or -name '*.pyi' -or -name '*.rst' \) | entr -d ./run_tests.sh $@; do sleep 1; done
