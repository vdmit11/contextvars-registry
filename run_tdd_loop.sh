#!/usr/bin/env sh

until find contextvars_extras -iname '*.py' | entr -d ./run_tests.sh; do sleep 1; done
