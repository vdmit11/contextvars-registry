import pytest

from contextvars_extras.sentinel import Sentinel


def test__Sentinel__checks_for_duplicate_names():
    Sentinel("some.module", "MISSING")

    with pytest.raises(AssertionError):
        Sentinel("some.module", "MISSING")

    Sentinel("some.module", "MISSING2")
    Sentinel("some.other.module", "MISSING")


def test__Sentinel__str_and_repr():
    MISSING = Sentinel("some.module2", "MISSING")
    assert str(MISSING) == "MISSING"
    assert repr(MISSING) == "some.module2.MISSING"


def test__Sentinel__is_falsy():
    MISSING = Sentinel("some.module3", "MISSING")
    assert not bool(MISSING)
