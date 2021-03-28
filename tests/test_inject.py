from contextvars import ContextVar

import pytest

from contextvars_extras.inject import inject_context_vars
from contextvars_extras.registry import ContextVarsRegistry


def test__inject_from_context_var_objects():
    timezone_var = ContextVar("my_project.namespace.timezone")
    locale_var = ContextVar("my_project.namespace.locale")

    @inject_context_vars(timezone_var, locale_var)
    def _get_values(locale, timezone="UTC"):
        return (locale, timezone)

    # pylint: disable=no-value-for-parameter
    with pytest.raises(TypeError):
        _get_values()

    locale_var.set("en")

    assert _get_values() == ("en", "UTC")

    assert _get_values(locale="en_GB") == ("en_GB", "UTC")
    assert _get_values(timezone="GMT") == ("en", "GMT")
    assert _get_values("en_GB", "GMT") == ("en_GB", "GMT")


def test__inject_vars_from_registry():
    class Current(ContextVarsRegistry):
        locale: str
        timezone: str = "UTC"

    current = Current()

    @inject_context_vars(current)
    def _get_values(locale="en", timezone="America/Troll", user_id=None):
        return (locale, timezone, user_id)

    # pass no args, then injector will only set timezone='UTC'
    # (the other two args are not set in the registry, so they're not injected)
    assert _get_values() == ("en", "UTC", None)

    # pass all positional args, and ensure injector won't override them
    assert _get_values("en_GB", "GMT", 42) == ("en_GB", "GMT", 42)

    # pass all keyword args, and ensure that injector won't override them
    assert _get_values(user_id=42, locale="en_GB", timezone="GMT") == ("en_GB", "GMT", 42)

    # set 'current.user_id', and ensure that injector could see it
    # (even though initially this context variable didn't exist in the registry)
    with current(user_id=1001):
        assert _get_values() == ("en", "UTC", 1001)

    # Try deep overriding of registry vars,
    # and ensure that injector could see values combined from all levels.
    with current(locale="en_GB"):
        with current(timezone="GMT", user_id=1):
            with current(timezone="Antarctica/Troll", user_id=None):
                assert _get_values() == ("en_GB", "Antarctica/Troll", None)
