import pytest

from contextvars_extras.util import Sentinel


def test__Sentinel__checks_for_duplicate_names():
    Sentinel("some.module", "Missing")

    with pytest.raises(AssertionError):
        Sentinel("some.module", "Missing")

    Sentinel("some.module", "Missing2")
    Sentinel("some.other.module", "Missing")


def test__Sentinel__str_and_repr():
    Missing = Sentinel("some.module2", "Missing")
    assert str(Missing) == "Missing"
    assert repr(Missing) == "some.module2.Missing"


def test__Sentinel__is_falsy():
    Missing = Sentinel("some.module3", "Missing")
    assert not bool(Missing)
