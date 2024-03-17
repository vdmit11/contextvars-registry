#!/usr/bin/env sh

set -e
set -x

poetry run isort contextvars_registry tests
poetry run black contextvars_registry tests
