#!/usr/bin/env sh

set -e

pylama ./contextvars_extras
pytest
