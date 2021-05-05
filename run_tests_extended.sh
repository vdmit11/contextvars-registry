#!/usr/bin/env sh

set -e

./run_tests.sh $@
tox
