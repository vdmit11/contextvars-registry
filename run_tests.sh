#!/usr/bin/env sh

echo '----------------'

set -e
set -x

poetry run pytest --cov=contextvars_registry --cov-fail-under=100 $@
