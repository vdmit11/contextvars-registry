#!/usr/bin/env sh

echo '----------------'

set -e
set -x

pylama ./contextvars_extras
pytest
