#!/usr/bin/env sh

set -e

./run_tests.sh $@
poetry run tox
