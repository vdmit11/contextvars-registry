#!/usr/bin/env sh

echo '----------------'

set -e
set -x

pylava ./contextvars_extras
pytest
