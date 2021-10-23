#!/usr/bin/env sh

echo '----------------'

set -e
set -x

pytest --cov=contextvars_extras --cov-fail-under=100 $@
