#!/usr/bin/env sh

set -e
set -x

poetry run isort contextvars_extras tests
poetry run black contextvars_extras tests
