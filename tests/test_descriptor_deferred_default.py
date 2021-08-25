import pytest

from contextvars_extras.context import bind_to_sandbox_context
from contextvars_extras.descriptor import ContextVarDescriptor


def test__deferred_default__is_called_by_get_method__once_per_context():
    def _empty_dict():
        _empty_dict.call_counter += 1
        return dict()

    _empty_dict.call_counter = 0

    test_dict_var = ContextVarDescriptor("test_dict_var", deferred_default=_empty_dict)

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
        return dict()

    _empty_dict.call_counter = 0

    test_dict_var = ContextVarDescriptor("test_dict_var", deferred_default=_empty_dict)

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
        ContextVarDescriptor("test_var", default={}, deferred_default=dict)
