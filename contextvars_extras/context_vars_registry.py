import threading
from collections.abc import ItemsView, KeysView, ValuesView
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, List, MutableMapping, Tuple, get_type_hints

from contextvars_extras.context_var_descriptor import ContextVarDescriptor
from contextvars_extras.context_var_ext import CONTEXT_VAR_VALUE_DELETED, NO_DEFAULT, Token
from contextvars_extras.internal_utils import ExceptionDocstringMixin


class ContextVarsRegistry(MutableMapping[str, Any]):
    """A collection of ContextVar() objects, with nice @property-like way to access them."""

    _registry_auto_create_vars: bool = True
    """Automatically create ContextVar() objects when setting attributes?

    If set to True (default), missing ContextVar() objects are automatically created when
    setting attributes. That is, you can define an empty class, and then set arbitrary attributes:

        >>> class CurrentVars(ContextVarsRegistry):
        ...    pass

        >>> current = CurrentVars()
        >>> current.locale = 'en'
        >>> current.timezone = 'UTC'

    However, if you find this behavior weak, you may disable it, like this:

        >>> class CurrentVars(ContextVarsRegistry):
        ...     _registry_auto_create_vars = False
        ...     locale: str = 'en'

        >>> current = CurrentVars()
        >>> current.timezone = 'UTC'
        AttributeError: ...
    """

    _registry_descriptors: Dict[str, ContextVarDescriptor]
    """A dictionary of all context vars in the registry.

    Keys are attribute names, and values are instances of :class:`ContextVarDescriptor`.

    The dictionary can be mutated at run time, because new variables can be created on the fly.

    Actually, this dictionary isn't strictly required.
    You can derive this mapping by iterating over all class attributes and calling isinstance().
    It is just kept for the convenience, and maybe small performance improvements.
    """

    _registry_var_create_lock: threading.RLock
    """A lock that protects against race conditions during cration of new ContextVar() objects.

    ContextVar() objects are lazily created on 1st attempt to set an attribute.
    So a race condition is possible: multiple concurrent threads (or co-routines)
    set an attribute for the 1st time, and thus create multiple ContextVar() objects.
    The last created ContextVar() object wins, and others are lost, causing a memory leak.

    So this lock is needed to ensure that ContextVar() object is created only once.
    """

    @contextmanager
    def __call__(self, **attr_names_and_values):
        """Set attributes temporarily, using context manager (the ``with`` statement in Python).

        Example of usage:

            >>> class CurrentVars(ContextVarsRegistry):
            ...     timezone: str = 'UTC'
            ...     locale: str = 'en'
            >>> current = CurrentVars()

            >>> with current(timezone='Europe/London', locale='en_GB'):
            ...    print(current.timezone)
            ...    print(current.locale)
            Europe/London
            en_GB

        On exiting form the ``with`` block, the values are restored:

            >>> current.timezone
            'UTC'
            >>> current.locale
            'en'

        .. caution::
            Only attributes that are present inside ``with (...)`` parenthesis are restored:

                >>> with current(timezone='Europe/London'):
                ...   current.locale = 'en_GB'
                ...   current.user_id = 42
                >>> current.timezone  # restored
                'UTC'
                >>> current.locale  # not restored
                'en_GB'
                >>> current.user_id  # not restored
                42

            That is, the ``with current(...)`` doesn't make a full copy of all context variables.
            It is NOT a scope isolation mechanism that protects all attributes.

            It is a more primitive tool, roughly, a syntax sugar for this:

                >>> try:
                ...     saved_timezone = current.timezone
                ...     current.timezone = 'Europe/London'
                ...
                ...     # do_something_useful_with_current_timezone()
                ... finally:
                ...     current.timezone = saved_timezone
        """
        saved_state: List[Tuple[ContextVarDescriptor, Token]] = []
        try:
            # Set context variables, saving their state.
            for attr_name, value in attr_names_and_values.items():
                # This is almost like __setattr__(), except that it also saves a Token() object,
                # that allows to restore the previous value later (via ContextVar.reset() method).
                descriptor = self.__before_set__ensure_initialized(attr_name, value)
                reset_token = descriptor.set(value)  # calls ContextVar.set() method
                saved_state.append((descriptor, reset_token))

            # execute code inside the ``with: ...`` block
            yield
        finally:
            # Restore context variables.
            for (descriptor, reset_token) in saved_state:
                descriptor.reset(reset_token)  # calls ContextVar.reset() method

    def __init_subclass__(cls):
        cls.__ensure_subclassed_properly()
        cls._registry_descriptors = {}
        cls._registry_var_create_lock = threading.RLock()
        cls.__init_type_hinted_class_attrs_as_descriptors()
        super().__init_subclass__()

    @classmethod
    def __ensure_subclassed_properly(cls):
        if ContextVarsRegistry not in cls.__bases__:
            raise RegistryInheritanceError

    # There is a bug in Pylint that gives false-positive warnings for classmethods below.
    # So, I have to mask that warning completely and wait until the bug in Pylint is fied.
    # pylint: disable=unused-private-member

    @classmethod
    def __init_type_hinted_class_attrs_as_descriptors(cls):
        hinted_attrs = get_type_hints(cls)
        for attr_name in hinted_attrs:
            cls.__init_class_attr_as_descriptor(attr_name)

    @classmethod
    def __init_class_attr_as_descriptor(cls, attr_name):
        with cls._registry_var_create_lock:
            if attr_name.startswith("_registry_"):
                return

            assert attr_name not in cls._registry_descriptors

            value = getattr(cls, attr_name, NO_DEFAULT)
            assert not isinstance(value, (ContextVar, ContextVarDescriptor))

            descriptor: ContextVarDescriptor = ContextVarDescriptor(default=value)
            descriptor.__set_name__(cls, attr_name)
            setattr(cls, attr_name, descriptor)
            cls._registry_descriptors[attr_name] = descriptor

    def __init__(self):
        self.__ensure_subclassed_properly()
        super().__init__()

    def __setattr__(self, attr_name, value):
        self.__before_set__ensure_initialized(attr_name, value)
        super().__setattr__(attr_name, value)

    @classmethod
    def __before_set__ensure_initialized(cls, attr_name, value) -> ContextVarDescriptor:
        try:
            return cls._registry_descriptors[attr_name]
        except KeyError:
            cls.__before_set__ensure_not_starts_with_special_registry_prefix(attr_name, value)
            cls.__before_set__initialize_attr_as_context_var_descriptor(attr_name, value)

            return cls._registry_descriptors[attr_name]

    @classmethod
    def __before_set__ensure_not_starts_with_special_registry_prefix(cls, attr_name, value):
        if attr_name.startswith("_registry_"):
            raise ReservedAttributeError.format(
                class_name=cls.__name__,
                attr_name=attr_name,
                attr_type=type(value).__name__,
                attr_value=value,
            )

    @classmethod
    def __before_set__initialize_attr_as_context_var_descriptor(cls, attr_name, value):
        assert (
            attr_name not in cls._registry_descriptors
        ), "This method should not be called when attribute is already initialized as ContextVar"

        if not cls._registry_auto_create_vars:
            raise UndeclaredAttributeError.format(
                class_name=cls.__name__,
                attr_name=attr_name,
                attr_type=type(value).__name__,
            )

        cls.__init_class_attr_as_descriptor(attr_name)

    # collections.abc.MutableMapping implementation methods

    @classmethod
    def _asdict(cls) -> Dict[str, Any]:
        out = {}
        for key, ctx_var in cls._registry_descriptors.items():
            try:
                out[key] = ctx_var.get()
            except LookupError:
                pass
        return out

    @classmethod
    def keys(cls) -> KeysView:
        """Get all variable names in the registry (excluding unset variables).

        Example::

            >>> class CurrentVars(ContextVarsRegistry):
            ...    locale: str = 'en'
            ...    timezone: str = 'UTC'

            >>> current = CurrentVars()

            >>> keys = current.keys()
            >>> list(keys)
            ['locale', 'timezone']
        """
        return cls._asdict().keys()

    @classmethod
    def values(cls) -> ValuesView:
        """Get values of all context variables in the registry.

        Example::

            >>> class CurrentVars(ContextVarsRegistry):
            ...    locale: str = 'en'
            ...    timezone: str = 'UTC'

            >>> current = CurrentVars()

            >>> values = current.values()
            >>> list(values)
            ['en', 'UTC']
        """
        return cls._asdict().values()

    @classmethod
    def items(cls) -> ItemsView:
        """Get key-value pairs for all context variables in the registry.

        Example::

            >>> class CurrentVars(ContextVarsRegistry):
            ...    locale: str = 'en'
            ...    timezone: str = 'UTC'

            >>> current = CurrentVars()

            >>> items = current.items()
            >>> list(items)
            [('locale', 'en'), ('timezone', 'UTC')]
        """
        return cls._asdict().items()

    @classmethod
    def __iter__(cls):
        return iter(cls._asdict())

    @classmethod
    def __len__(cls):
        return len(cls._asdict())

    @classmethod
    def __getitem__(cls, key):
        ctx_var = cls._registry_descriptors[key]
        try:
            return ctx_var.get()
        except LookupError as err:
            raise KeyError(key) from err

    @classmethod
    def __setitem__(cls, key, value):
        ctx_var = cls.__before_set__ensure_initialized(key, value)
        ctx_var.set(value)

    def __delitem__(self, key):
        ctx_var = self.__before_set__ensure_initialized(key, None)
        ctx_var.__delete__(self)


def save_context_vars_registry(
    registry: ContextVarsRegistry,
) -> Dict[str, Any]:
    """Dump variables from ContextVarsRegistry as dict.

    The resulting dict can be used as argument to :func:`restore_context_vars_registry`.
    """
    # pylint: disable=protected-access
    return {key: descriptor.get_raw() for key, descriptor in registry._registry_descriptors.items()}


def restore_context_vars_registry(
    registry: ContextVarsRegistry,
    saved_registry_state: Dict[str, Any],
):
    """Restore ContextVarsRegistry state from dict.

    The :func:`restore_context_vars_registry` restores state of :class:`ContextVarsRegistry`,
    using state that was previously dumped by :func:`save_context_vars_registry`.

    :param registry: a :class:`ContextVarsRegistry` instance that will be written
    :param saved_registry_state: output of :func:`save_context_vars_registry` function

    Example::

        >>> from contextvars_extras.context_vars_registry import (
        ...    ContextVarsRegistry,
        ...    save_context_vars_registry,
        ...    restore_context_vars_registry,
        ... )

        >>> class CurrentVars(ContextVarsRegistry):
        ...     locale: str = 'en'
        ...     timezone: str = 'UTC'

        >>> current = CurrentVars()
        >>> state1 = save_context_vars_registry(current)

        >>> current.locale = 'en_US'
        >>> current.timezone = 'America/New York'
        >>> state2 = save_context_vars_registry(current)

        >>> del current.locale
        >>> del current.timezone
        >>> current.user_id = 42
        >>> state3 = save_context_vars_registry(current)

        >>> restore_context_vars_registry(current, state1)
        >>> dict(current)
        {'locale': 'en', 'timezone': 'UTC'}

        >>> restore_context_vars_registry(current, state2)
        >>> dict(current)
        {'locale': 'en_US', 'timezone': 'America/New York'}

        >>> restore_context_vars_registry(current, state3)
        >>> dict(current)
        {'user_id': 42}

    A similar result could be achieved by the standard :class:`collections.abc.MutableMapping`
    methods, like ``registry.clear()`` and ``registry.update()``, but this is not exactly the same.
    There is still a couple of differences:

      1. :func:`save_registry_state` and :func:`restore_registry_state` can handle special cases,
         like ``CONTEXT_VAR_VALUE_DELETED`` tokens, or lazy initializers.

      2. :class:`collections.abc.MutableMapping` methods are slow, while
         :func:`save_registry_state` and :func:`restore_registry_state` are faster,
         since they can reach some registry internals directly, avoiding complex methods.

    .. Note::

        This function is not scalable, it takes O(N) time, where N is the number of variables
        in the registry.

        There is a faster tool, a decorator that saves/restores all context variables on each call,
        and that takes O(1) time: :func:`contextvars_extras.context.bind_to_sandbox_context`

        So you prefer that decorator by default, and choose :func:`restore_registry_state`
        only when you can't use the decorator, or when you need to restore only 1 specific
        registry, not touching variables outside of the registry.
    """
    get_saved_value = saved_registry_state.get

    # pylint: disable=protected-access
    for key, descriptor in registry._registry_descriptors.items():
        descriptor.context_var.set(get_saved_value(key, CONTEXT_VAR_VALUE_DELETED))


class RegistryInheritanceError(ExceptionDocstringMixin, TypeError):
    """Class ContextVarsRegistry must be subclassed, and only one level deep.

    This exception is raised in 2 cases:

    1. When you use :class:`ContextVarsRegistry` directly, without subclassing::

        instance = ContextVarsRegistry()

    2. When you create a sub-sub-class of ``ContextVarsRegistry``::

        class SubRegistry(ContextVarsRegistry):
            pass

        class SubSubRegistry(ContextVarsRegistry):
            pass

    These limitations are caused by the way we store ``ContextVar`` objects on class attributes.
    Setting a context variable on a base class pollutes all its sub-classes,
    and setting a variable on sub-class shadows attribute of the base class.
    Things become messy quickly, so we ensure you define subclasses in a right way.

    So, the proper way is to just define a subclass (but not sub-sub-class),
    and then use it, like this::

        class CurrentVars(ContextVarsRegistry):
            var1: str = "default_value"

        current = CurrentVars()
        current.var1   # => "default_value"

    .. NOTE::

      Actually, that could be done in a smarter way: what we really want is to make sure that
      ``ContextVar`` objects are always stored in the leafs of class hierarchy.
      So, we could forbid subclassing if a class has context variables, and also forbid
      setting variables on a class that has subclasses, and that should solve the problem.

      But, that could add some complexity, so to keep things simple, we just ban deep inheritance.
      At least for now (may be implemented in the future, or maybe not).
    """


class ReservedAttributeError(ExceptionDocstringMixin, AttributeError):
    """Can't set attribute: {class_name}.{attr_name} because of the special '_registry_' prefix.

    This exception is raised when you try to set a special attribute::

        instance.{attr_name} = {attr_value!r}

    The ``_registry_*`` prefix is reserved for configuration of the :class:`ContextVarRegistry`.
    You can't have a context variable with such name.

    If you want to configure the registry class itself, you should do it when defining
    your sub-class, like this::

        class {class_name}(ContextVarsRegistry):
            {attr_name}: {attr_type} = {attr_value!r}
    """


class UndeclaredAttributeError(ExceptionDocstringMixin, AttributeError):
    """Can't set undeclared attribute: '{class_name}.{attr_name}'.

    This exception is raised when you try to set an attribute that was not declared
    in the class {class_name} (subclass of :class:`ContextVarsRegistry`).

    And, the class {class_name} is configured in a specific way
    that disables dyanmic variable initialization::

        class {class_name}(ContextVarsRegistry):
            _registry_auto_create_vars = False

    Because of ``_registry_auto_create_vars=False``, you can use only pre-defined variables.
    An attempt to set any other attribute will raise this exception.

    So, you have 3 options to solve the problem:

    1. Add attribute to the class, like this::

        class {class_name}(ContextVarsRegistry):
            {attr_name}: {attr_type}

    2. Enable dynamic initialization of new context variables, like this::

        class {class_name}(ContextVarsRegistry):
            _registry_auto_create_vars = True

    3. Check the name of the attribute: '{attr_name}'.
       Maybe there is a typo in the name?
    """
