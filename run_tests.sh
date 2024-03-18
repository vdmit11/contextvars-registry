#!/usr/bin/env sh

echo '----------------'

set -e
set -x

ARGS=$@
SRC=${ARGS:-"contextvars_registry tests docs"}

ruff check $SRC
mypy $SRC
poetry run pytest --cov=contextvars_registry --cov-fail-under=100 $SRC
