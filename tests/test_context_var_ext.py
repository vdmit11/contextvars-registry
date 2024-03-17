from contextvars import ContextVar

import pytest

from contextvars_registry import ContextVarExt
from contextvars_registry.context_management import bind_to_sandbox_context


def test__deferred_default__is_called_by_get_method__once_per_context():
    call_counter = 0

    def _empty_dict():
        nonlocal call_counter
        call_counter += 1
        return {}

    test_dict_var = ContextVarExt("test_dict_var", deferred_default=_empty_dict)

    @bind_to_sandbox_context
    def modify_test_dict(**values):
        for key, value in values.items():
            # intentionally calling .get() many times to test that
            # ``deferred_default=_empty_dict`` is evaluated only once
            test_dict = test_dict_var.get()
            test_dict[key] = value

        return test_dict_var.get()

    assert modify_test_dict(foo=1, bar=2) == {"foo": 1, "bar": 2}
    assert modify_test_dict(a=1, b=2, c=3) == {"a": 1, "b": 2, "c": 3}

    assert call_counter == 2


def test__deferred_default__works_with__is_set__and__reset_to_default__methods():
    call_counter = 0

    def _empty_dict():
        nonlocal call_counter
        call_counter += 1
        return {}

    test_dict_var = ContextVarExt("test_dict_var", deferred_default=_empty_dict)

    assert not test_dict_var.is_set()
    assert call_counter == 0

    test_dict_var.get()
    assert test_dict_var.is_set()
    assert call_counter == 1

    test_dict_var.reset_to_default()
    assert not test_dict_var.is_set()
    assert call_counter == 1

    test_dict_var.get()
    assert test_dict_var.is_set()
    assert call_counter == 2


def test__deferred_default__cannot_be_used_with_just__default():
    with pytest.raises(AssertionError):
        ContextVarExt("test_var", default={}, deferred_default=dict)


def test__deferred_default__is_masked_by__default_arg_of_get_method():
    call_counter = 0

    def _empty_dict():
        nonlocal call_counter
        call_counter += 1
        return {}

    test_dict_var = ContextVarExt("test_dict_var", deferred_default=_empty_dict)

    # .get(default=...) arg is present, so deferred default is not called
    value = test_dict_var.get(default=None)
    assert value is None
    assert call_counter == 0


def test__deferred_default__cannot_be_used__if_existing_context_var_has_default_value():
    timezone_var: ContextVar[str] = ContextVar("timezone_var")
    timezone_var_ext = ContextVarExt.from_existing_var(timezone_var, deferred_default=lambda: "UTC")
    assert timezone_var_ext.get() == "UTC"

    # Same as above, but the existing ContextVar() object has a default value.
    # In this case, an exception is thrown, since default+deferred_default cannot be used together.
    timezone_var = ContextVar("timezone_var", default="UTC")
    with pytest.raises(AssertionError):
        ContextVarExt.from_existing_var(timezone_var, deferred_default=lambda: "GMT")
