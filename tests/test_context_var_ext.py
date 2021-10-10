import pytest

from contextvars_extras.context_management import bind_to_sandbox_context
from contextvars_extras.context_var_ext import ContextVarExt


def test__deferred_default__is_called_by_get_method__once_per_context():
    def _empty_dict():
        _empty_dict.call_counter += 1
        return {}

    _empty_dict.call_counter = 0

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

    assert _empty_dict.call_counter == 2


def test__deferred_default__works_with__is_set__and__reset_to_default__methods():
    def _empty_dict():
        _empty_dict.call_counter += 1
        return {}

    _empty_dict.call_counter = 0

    test_dict_var = ContextVarExt("test_dict_var", deferred_default=_empty_dict)

    assert not test_dict_var.is_set()
    assert _empty_dict.call_counter == 0

    test_dict_var.get()
    assert test_dict_var.is_set()
    assert _empty_dict.call_counter == 1

    test_dict_var.reset_to_default()
    assert not test_dict_var.is_set()
    assert _empty_dict.call_counter == 1

    test_dict_var.get()
    assert test_dict_var.is_set()
    assert _empty_dict.call_counter == 2


def test__deferred_default__cannot_be_used_with_just__default():
    with pytest.raises(AssertionError):
        ContextVarExt("test_var", default={}, deferred_default=dict)


def test__deferred_default__is_masked_by__default_arg_of_get_method():
    def _empty_dict():
        _empty_dict.call_counter += 1
        return {}

    _empty_dict.call_counter = 0

    test_dict_var = ContextVarExt("test_dict_var", deferred_default=_empty_dict)

    # .get(default=...) arg is present, so deferred default is not called
    value = test_dict_var.get(default=None)
    assert value is None
    assert _empty_dict.call_counter == 0


def test__context_var_ext__has_optimized_method_stubs():
    # This test doesn't test anything useful.
    # It is only needed to achieve 100% test coverage.
    #
    # It just triggers some code that is never executed under normal circumstances
    # (it is never executed because methods are replaced with performance-boosted closures
    # when the ContextVarExt class is instanciated).
    # So here we just trigger empty method stubs just to achieve 100% test coverage.

    timezone_var = ContextVarExt("timezone_var", default="UTC")

    with pytest.raises(AssertionError):
        ContextVarExt.get(timezone_var)

    with pytest.raises(AssertionError):
        ContextVarExt.get_raw(timezone_var)

    with pytest.raises(AssertionError):
        ContextVarExt.is_set(timezone_var)

    with pytest.raises(AssertionError):
        ContextVarExt.set(timezone_var, "GMT")

    token = timezone_var.set("GMT")
    with pytest.raises(AssertionError):
        ContextVarExt.reset(timezone_var, token)
