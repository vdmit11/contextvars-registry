#!/usr/bin/env sh

echo '----------------'

set -e
set -x

pylava
pytest
