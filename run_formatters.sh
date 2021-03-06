#!/usr/bin/env sh

set -e
set -x

isort contextvars_extras tests
black contextvars_extras tests
