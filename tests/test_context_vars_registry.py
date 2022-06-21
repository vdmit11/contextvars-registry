import functools
from typing import ClassVar, Optional

from pytest import raises

from contextvars_extras import ContextVar, ContextVarDescriptor, ContextVarsRegistry
from contextvars_extras.context_var_ext import RESET_TO_DEFAULT
from contextvars_extras.context_vars_registry import RegistryInheritanceError

# pylint: disable=attribute-defined-outside-init,protected-access,pointless-statement
# pylint: disable=function-redefined


def test__ContextVarsRegistry__must_be_subclassed__but_not_subsubclassed():
    # First, let's demonstrate a normal use of ContextVarsRegistry:
    # you create a sub-class of it, and then can use it, like set a variable.
    # That should work as usual and not raise any exceptions.
    class SubRegistry(ContextVarsRegistry):
        pass

    sub_registry = SubRegistry()
    sub_registry.some_var = "value"  # type: ignore[attr-defined]

    # But, sub-sub-classing is not allowed
    with raises(RegistryInheritanceError):
        # pylint: disable=unused-variable
        class SubSubRegistry(SubRegistry):
            pass

    # Instanciating ContextVarsRegistry directly (without subclassing) is also not allowed.
    with raises(RegistryInheritanceError):
        ContextVarsRegistry()


def test__type_hinted_attrs__automatically_converted_to__context_var_descriptor():
    class MyVars(ContextVarsRegistry):
        hinted: str

    # When subclassed, the .hinted attribute magically becomes a ContextVarDescriptor object
    assert isinstance(MyVars.hinted, ContextVarDescriptor)

    # at instance level, descriptors do proxy calls to ContextVar.get()/ContextVar.set() methods
    my_vars = MyVars()

    # The context variable isn't set yet, so initially it throws  AttributeError
    with raises(AttributeError):
        my_vars.hinted

    # Set the attribute, and now the context variable becomes set.
    my_vars.hinted = "foo"
    assert my_vars.hinted == "foo"

    # At class level, descriptors can be used to call .get()/.set()/.reset() on a ContextVar.
    assert MyVars.hinted.get() == "foo"

    token = MyVars.hinted.set("bar")
    assert my_vars.hinted == MyVars.hinted.get() == "bar"

    MyVars.hinted.reset(token)
    assert my_vars.hinted == MyVars.hinted.get() == "foo"

    # underlying ContextVar() objects are available via ContextVarDescriptor.context_var
    assert isinstance(MyVars.hinted.context_var, ContextVar)

    # also, ContextVar() automatically get verbose name, useful for debugging
    assert (
        "tests.test_context_vars_registry.MyVars.hinted"
        == MyVars.hinted.name
        == MyVars.hinted.context_var.name
    )


def test__attributes_hinted_with_ClassVar__are_NOT_converted_to_context_vars():
    class MyVars(ContextVarsRegistry):
        hinted_with_str: str = "hinted_with_str"
        hinted_with_ClassVar_str: ClassVar[str] = "hinted_with_ClassVar_str"

    assert isinstance(MyVars.hinted_with_str, ContextVarDescriptor)
    assert isinstance(MyVars.hinted_with_ClassVar_str, str)


def test__some_attributes_wihout_type_hints__are_converted_to_context_vars():  # noqa: R701
    class MyVars(ContextVarsRegistry):
        var1 = "var1 value"
        _var2 = "var2 value"
        __var3 = "var3 value"
        var4 = ContextVarDescriptor(default="var4 value")

        __special_attr__ = "special attr value"

        @property
        def some_property(self):
            return self.__var3

        def some_method(self):
            return self.__var3

        @classmethod
        def some_class_method(cls):
            return cls.__var3

        some_lambda = lambda x: x  # noqa
        some_partial = functools.partial(some_lambda)
        some_partialmethod = functools.partialmethod(some_method)

    # all regular variables are converted to context var (even ones with underscore prefix)
    assert isinstance(MyVars.var1, ContextVarDescriptor)
    assert isinstance(MyVars._var2, ContextVarDescriptor)
    assert isinstance(MyVars._MyVars__var3, ContextVarDescriptor)  # type: ignore

    # var4 is already a ContextVarDescriptor, so check that it is NOT wrapped in another context var
    assert isinstance(MyVars.var4.get(), str)

    # special attributes are NOT converted to context vars
    assert not isinstance(MyVars.__special_attr__, ContextVarDescriptor)
    assert not isinstance(MyVars._abc_impl, ContextVarDescriptor)  # type: ignore

    # properties and methods are NOT converted
    assert not isinstance(MyVars.some_property, ContextVarDescriptor)
    assert not isinstance(MyVars.some_method, ContextVarDescriptor)
    assert not isinstance(MyVars.some_class_method, ContextVarDescriptor)

    # NOTE: lambdas and partial() objects are converted!
    assert isinstance(MyVars.some_lambda, ContextVarDescriptor)
    assert isinstance(MyVars.some_partial, ContextVarDescriptor)  # type: ignore

    # ...but partialmethod() is not converted (because you usually use it as a method, not a value)
    assert not isinstance(MyVars.some_partialmethod, ContextVarDescriptor)


def test__registry_settings__are_NOT_converted_to_context_vars():
    class MyVars(ContextVarsRegistry):
        _registry_allocate_on_setattr = False

    assert isinstance(MyVars._registry_allocate_on_setattr, bool)


def test__class_member_values__become__context_var_defaults():
    class MyVars(ContextVarsRegistry):
        has_default: str = "has default value"
        has_none_as_default: Optional[int] = None
        no_default: Optional[str]

    my_vars = MyVars()

    assert my_vars.has_default == "has default value"
    assert my_vars.has_none_as_default is None

    # an attempt to get value of an unitialized variable raises an exception
    # It is not a bug. It is a feature: "default=None" and "no default at all" are 2 separate cases.
    with raises(LookupError):
        my_vars.no_default

    # after we initialize it, the error is not raised anymore
    my_vars.no_default = None
    assert my_vars.no_default is None


def test__missing_vars__are_automatically_created__on_setattr():
    class CurrentVars(ContextVarsRegistry):
        pass

    current = CurrentVars()

    with raises(AttributeError):
        current.timezone  # type: ignore[attr-defined]
    current.timezone = "Europe/Moscow"  # type: ignore[attr-defined]
    assert CurrentVars.timezone.get() == "Europe/Moscow"  # type: ignore[attr-defined]

    # ...but this feature may be disabled by setting `_registry_allocate_on_setattr = False`
    # Let's test that:

    class CurrentVars(ContextVarsRegistry):  # type: ignore[no-redef]
        _registry_allocate_on_setattr = False

    current = CurrentVars()

    with raises(AttributeError):
        current.timezone = "Europe/Moscow"  # type: ignore[attr-defined]


def test__setattr__does_NOT_overwrite_existing_class_members():
    class CurrentVars(ContextVarsRegistry):
        class_var: ClassVar[str]

        def method(self):
            return self.class_var

    current = CurrentVars()

    # attributes annotated with ClassVar cannot be converted to context variables
    with raises(AttributeError):
        current.class_var = "some value"  # type: ignore

    # methods cannot be overwritten with context variables
    with raises(AttributeError):
        current.method = lambda self: 42  # type: ignore

    # special attributes cannot be context variables as well
    with raises(AttributeError):
        current.__doc__ = "foo"

    # another special attribute
    with raises(AttributeError):
        current._abc_impl = None  # type: ignore[attr-defined]


def test__with_context_manager__sets_variables__temporarily():
    class CurrentVars(ContextVarsRegistry):
        timezone: str = "UTC"
        locale: str

    current = CurrentVars()

    with current(timezone="Europe/London", locale="en"):
        with current(locale="en_GB", user_id=1):
            assert current.timezone == "Europe/London"
            assert current.locale == "en_GB"
            assert current.user_id == 1  # type: ignore[attr-defined]
        assert current.timezone == "Europe/London"
        assert current.locale == "en"
        assert CurrentVars.user_id.get("FALLBACK") == "FALLBACK"  # type: ignore[attr-defined]

        # ``user_id`` wasn't set above using the ``with()`` block,
        # so it will NOT be restored afterrwards
        current.user_id = 2  # type: ignore[attr-defined]

    # not restored, because not present in the ``with (...)`` parenthesis
    assert current.user_id == 2  # type: ignore[attr-defined]

    # these two were set using ``with (...)``, so they are restored to their initial states
    assert current.timezone == "UTC"
    assert CurrentVars.locale.get("FALLBACK") == "FALLBACK"  # type: ignore[attr-defined]


def test__with_context_manager__throws_error__when_setting_class_members():
    class CurrentVars(ContextVarsRegistry):
        some_class_var: ClassVar[str] = "not a ContextVar because of special ClassVar annotation"

        @property
        def some_property(self):
            return self.some_class_var

        def some_method(self):
            return self.some_class_var

    current = CurrentVars()

    with raises(AttributeError):
        with current(some_class_var="foo"):
            pass

    with raises(AttributeError):
        with current(some_property=42):
            pass

    with raises(AttributeError):
        with current(some_method=lambda self: 42):
            pass

    with raises(AttributeError):
        with current(__doc__="new docs"):
            pass

    with raises(AttributeError):
        with current(_abc_impl=None):
            pass


def test__with_context_manager__throws_error__when_init_on_setattr_is_disabled():
    class CurrentVars(ContextVarsRegistry):
        _registry_allocate_on_setattr = False
        locale: str = "en"

    current = CurrentVars()

    with current(locale="en_US"):
        assert current.locale == "en_US"

    # an attempt to set current.timezone will raise AttributeError
    # Because the variable wasn't declared in the class definition
    # (and dynamic creation of variables is disabled by ``_registry_allocate_on_setattr = False``)
    with raises(AttributeError):
        with current(locale="en_US", timezone="America/New_York"):
            pass


def test__with_context_manager__restores_attrs__even_if_exception_is_raised():
    class CurrentVars(ContextVarsRegistry):
        locale: str = "en"

    current = CurrentVars()

    # Try to set a couple of attributes using the ``with`` statement.
    #
    # Upon exit from the ``with`` block, the attribute states must be restored,
    # even though ValueError was raised inside.
    with raises(ValueError):
        with current(locale="en_US", user_id=42):
            raise ValueError

    # current.locale is restored to the default value
    assert current.locale == "en"

    # current.user_id is also restored to its initial state:(no value, getattr raises LookupError)
    with raises(LookupError):
        current.user_id  # type: ignore[attr-defined]


def test__with_context_manager__can_also_set_properties():
    class CurrentVars(ContextVarsRegistry):
        _locale: str
        _timezone: str = "utc"

        @property
        def locale(self):
            return self._locale

        @locale.setter
        def locale(self, new_locale):
            self._locale = new_locale

        @locale.deleter
        def locale(self):
            del self._locale

        @property
        def timezone(self):
            return self._timezone.upper()

        @timezone.setter
        def timezone(self, new_timezone):
            assert new_timezone
            self._timezone = new_timezone

    current = CurrentVars()

    with current(locale="en_GB", timezone="gmt"):
        assert current.locale == "en_GB"
        assert current.timezone == "GMT"

    assert not hasattr(current, "locale")
    assert current.timezone == "UTC"


def test__ContextVarsRegistry__calls_super_in_init_methods():
    class MyMixin:
        init_was_called: bool = False
        init_subclass_was_called: bool = False

        def __init_subclass__(cls):
            assert isinstance(cls, type)
            MyMixin.init_subclass_was_called = True
            super().__init_subclass__()

        def __init__(self):
            MyMixin.init_was_called = True
            super().__init__()

    class CurrentVars(ContextVarsRegistry, MyMixin):
        pass

    CurrentVars()

    assert MyMixin.init_subclass_was_called
    assert MyMixin.init_was_called


def test__hasattr_getattr_setattr_consistency():  # noqa R701
    class CurrentVars(ContextVarsRegistry):
        # Here we test 3 different cases of variables:
        #  1. declared and initialized with a default value
        locale: str = "en"
        #  2. declared, but not initialized
        timezone: str
        #  3. not declared (will be allocated automatically when attribute is set)
        # user_id: int

    current = CurrentVars()
    _MISSING = object()

    # Initially, only 'locale' attribute is set, and the other two attributes are missing.
    # Well, actually, ContextVar() objects may alrady be allocated, and stored in class
    # attributes, but for consistency, the class behaves as if attributes were never set.
    assert hasattr(current, "locale") is True
    assert hasattr(current, "timezone") is False
    assert hasattr(current, "user_id") is False
    assert getattr(current, "locale", _MISSING) == "en"
    assert getattr(current, "timezone", _MISSING) is _MISSING
    assert getattr(current, "user_id", _MISSING) is _MISSING

    # Try with() block that sets values temporarily.
    # Inside the ``with`` block, attributes should be set and accessible via ``getattr()``,
    # but upon exit from the block, the state should be restored, as if they were never set.
    with current(locale="en", timezone="UTC", user_id=1):
        assert hasattr(current, "locale") is True
        assert hasattr(current, "timezone") is True
        assert hasattr(current, "user_id") is True
        assert getattr(current, "locale") == "en"
        assert getattr(current, "timezone") == "UTC"
        assert getattr(current, "user_id") == 1

    # Upon exit from the block, the initial state should be restored.
    assert hasattr(current, "locale") is True
    assert hasattr(current, "timezone") is False
    assert hasattr(current, "user_id") is False
    assert getattr(current, "locale", _MISSING) == "en"
    assert getattr(current, "timezone", _MISSING) is _MISSING
    assert getattr(current, "user_id", _MISSING) is _MISSING

    # Try to set some attributes. hasattr()/getattr() should see these changes.
    current.locale = "en_GB"
    current.timezone = "Europe/London"
    current.user_id = 42  # type: ignore[attr-defined]
    assert hasattr(current, "locale") is True
    assert hasattr(current, "timezone") is True
    assert hasattr(current, "user_id") is True
    assert getattr(current, "locale") == "en_GB"
    assert getattr(current, "timezone") == "Europe/London"
    assert getattr(current, "user_id") == 42


def test__deleting_attributes__is_allowed__but_under_the_hood_there_is_special_sentinel_object():
    class CurrentVars(ContextVarsRegistry):
        locale: str = "en"
        timezone: str

    current = CurrentVars()

    current.locale
    del current.locale
    with raises(AttributeError):
        current.locale

    with raises(AttributeError):
        del current.locale

    with raises(AttributeError):
        del current.timezone


def test__ContextVarsRegistry__can_act_like_dict():  # noqa R701
    class CurrentVars(ContextVarsRegistry):
        locale: str = "en"
        timezone: str
        user_id: int

    current = CurrentVars()

    # get item
    assert current["locale"] == "en"

    # .get() method
    assert current.get("locale") == "en"
    assert current.get("timezone", "DEFAULT_VALUE") == "DEFAULT_VALUE"

    # set item
    current["locale"] = "en_US"
    assert current["locale"] == "en_US"

    # .setdefault() method
    assert current.setdefault("locale", "en_GB") == "en_US"
    assert current["locale"] == "en_US"

    # .update() method
    current.update(
        {
            "locale": "en_GB",
            "timezone": "GMT",
        }
    )
    assert current["locale"] == "en_GB"
    assert current["timezone"] == "GMT"

    # converting to dict()
    assert dict(current) == {
        "locale": "en_GB",
        "timezone": "GMT",
    }

    # counting variables (note: 'user_id' variable doesn't have a value, so not counted)
    assert len(current) == 2

    # iter()
    assert list(iter(current)) == ["locale", "timezone"]

    # keys()/values()/items()
    assert set(current.keys()) == {"locale", "timezone"}
    assert set(current.values()) == {"en_GB", "GMT"}
    assert set(current.items()) == {("locale", "en_GB"), ("timezone", "GMT")}

    # `del` operator
    del current["locale"]
    with raises(KeyError):
        del current["locale"]
    with raises(KeyError):
        current["locale"]
    current["locale"] = "en_GB"

    # .pop()
    assert current.pop("locale") == "en_GB"
    with raises(KeyError):
        current.pop("locale")
    current["locale"] = "en_GB"

    # .popitem()
    assert current.popitem() == ("locale", "en_GB")
    assert current.popitem() == ("timezone", "GMT")
    with raises(KeyError):
        current.popitem()

    current.update({"locale": "en_GB", "timezone": "GMT"})

    # error/edge cases...

    # an attempt ro read a non-existent variable throws an error
    with raises(KeyError):
        current["non_existent_context_var"]

    # an attempt to delete a non-existent variable throws an error
    with raises(KeyError):
        del current["another_non_existent_context_var"]

    # an attempt to read non-initialized (but still existing) context variable throws an error
    assert CurrentVars.user_id
    with raises(KeyError):
        current["user_id"]

    # an attempt to delete a non-initialized (but still existing) variable throws an error
    with raises(KeyError):
        del current["user_id"]

    # the with() context manager is friendly towards those dict methods....
    with current(locale="nb", timezone="Antarctica/Troll", user_id=42, name="John Doe"):
        current.update({"user_id": 43, "name": "John Smith"})

        assert dict(current) == {
            "locale": "nb",
            "timezone": "Antarctica/Troll",
            "user_id": 43,
            "name": "John Smith",
        }

    # also, state is restored nicely upon exit form the with(...) block
    assert dict(current) == {
        "locale": "en_GB",
        "timezone": "GMT",
    }
    assert "user_id" not in current
    assert "last_name" not in current


def test__dict_keys_method__does_NOT_trigger__deferred_default():
    class CurrentVars(ContextVarsRegistry):
        timezone = ContextVarDescriptor(deferred_default=lambda: "UTC")

    current = CurrentVars()
    assert CurrentVars.timezone.get_raw() == RESET_TO_DEFAULT

    # .keys() does NOT trigger deferred_default
    current.keys()
    assert CurrentVars.timezone.get_raw() == RESET_TO_DEFAULT

    # ...but .values() does
    print(current.values())
    assert CurrentVars.timezone.get_raw() == "UTC"
