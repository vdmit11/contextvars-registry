from __future__ import annotations

import threading
from collections.abc import ItemsView, KeysView, MutableMapping, ValuesView
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Dict, List, Tuple, get_type_hints

from contextvars_extras.descriptor import ContextVarDescriptor
from contextvars_extras.util import ExceptionDocstringMixin, Missing


class ContextVarsRegistry(MutableMapping):
    """A collection of ContextVar() objects, with nice @property-like way to access them.

    The idea is simple: you create a sub-class, and declare your variables using type annotations:

        >>> class CurrentVars(ContextVarsRegistry):
        ...    locale: str = 'en_GB'
        ...    timezone: str = 'Europe/London'
        ...    user_id: int = None
        ...    db_session: object

        >>> current = CurrentVars()

    When you create a sub-class, all type-hinted members become ContextVar() objects,
    and you can work with them by just getting/setting instance attributes:

        >>> current.locale
        'en_GB'

        >>> current.timezone
        'Europe/London'

        >>> current.timezone = 'UTC'
        >>> current.timezone
        'UTC'

    Getting/setting attributes is automatically mapped to ContextVar.get()/ContextVar.set() calls.

    The underlying ContextVar() objects can be managed via class attributes:

        >>> CurrentVars.timezone.get()
        'UTC'

        >>> token = CurrentVars.timezone.set('GMT')
        >>> current.timezone
        'GMT'
        >>> CurrentVars.timezone.reset(token)
        >>> current.timezone
        'UTC'

    Well, actually, the above is a little lie: the class members are actially instances of
    ContextVarDescriptor (not ContextVar). It has all the same get()/set()/reset() methods, but it
    is not a subclass (just because ContextVar can't be subclassed, this is a technical limitation).

    So class members are ContextVarDescriptor objects:

        >>> CurrentVars.timezone
        <ContextVarDescriptor name='contextvars_extras.registry.CurrentVars.timezone'>

    and its underlying ContextVar can be reached via the `.context_var` attribute:

        >>> CurrentVars.timezone.context_var
        <ContextVar name='contextvars_extras.registry.CurrentVars.timezone'...>

    But in practice, you normally shouldn't need that.
    ContextVarDescriptor should implement all same attributes and methods as ContextVar,
    and thus it can be used instead of ContextVar() object in all cases except isinstance() checks.
    """

    _var_init_on_setattr: bool = True
    """Automatically initialize missing ContextVar() objects when setting attributes?

    If set to True (default), missing ContextVar() objects are automatically created when
    setting attributes. That is, you can define an empty class, and then set arbitrary attributes:

        >>> class CurrentVars(ContextVarsRegistry):
        ...    pass

        >>> current = CurrentVars()
        >>> current.locale = 'en'
        >>> current.timezone = 'UTC'

    However, if you find this behavior weak, you may disable it, like this:

        >>> class CurrentVars(ContextVarsRegistry):
        ...     _var_init_on_setattr = False
        ...     locale: str = 'en'

        >>> current = CurrentVars()
        >>> current.timezone = 'UTC'
        AttributeError: ...
    """

    _var_init_done_descriptors: Dict[str, ContextVarDescriptor]
    """A dictionary that tracks which attributes were initialized as ContextVarDescriptor objects.

    Keys are attribute names, and values are instances of :class:`ContextVarDescriptor`.
    The dictionary can be mutated at run time, because new context variables can be created
    on the fly, lazily, on 1st set of an attribute.

    Actually, this dictionary isn't strictly required.
    You can derive this mapping by iterating over all class attributes and calling isinstance().
    It is just kept for the convenience, and maybe small performance improvements.
    """

    _var_init_lock: threading.RLock
    """A lock that protects initialization of the class attributes as context variables.

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
        cls._var_init_done_descriptors = dict()
        cls._var_init_lock = threading.RLock()
        cls.__init_type_hinted_class_attrs_as_descriptors()
        super().__init_subclass__()

    @classmethod
    def __ensure_subclassed_properly(cls):
        if ContextVarsRegistry not in cls.__bases__:
            raise RegistryInheritanceError

    @classmethod
    def __init_type_hinted_class_attrs_as_descriptors(cls):
        hinted_attrs = get_type_hints(cls)
        for attr_name in hinted_attrs:
            cls.__init_class_attr_as_descriptor(attr_name)

    @classmethod
    def __init_class_attr_as_descriptor(cls, attr_name):
        with cls._var_init_lock:
            if attr_name in cls._var_init_done_descriptors:
                return

            if attr_name.startswith("_var_"):
                return

            value = getattr(cls, attr_name, Missing)
            assert not isinstance(value, (ContextVar, ContextVarDescriptor))

            descriptor = ContextVarDescriptor(default=value, owner_cls=cls, owner_attr=attr_name)
            setattr(cls, attr_name, descriptor)
            cls._var_init_done_descriptors[attr_name] = descriptor

    def __init__(self):
        self.__ensure_subclassed_properly()
        super().__init__()

    def __setattr__(self, attr_name, value):
        self.__before_set__ensure_initialized(attr_name, value)
        super().__setattr__(attr_name, value)

    @classmethod
    def __before_set__ensure_initialized(cls, attr_name, value) -> ContextVarDescriptor:
        try:
            return cls._var_init_done_descriptors[attr_name]
        except KeyError:
            cls.__before_set__ensure_not_starts_with_special_var_prefix(attr_name, value)
            cls.__before_set__initialize_attr_as_context_var_descriptor(attr_name, value)

            return cls._var_init_done_descriptors[attr_name]

    @classmethod
    def __before_set__ensure_not_starts_with_special_var_prefix(cls, attr_name, value):
        if attr_name.startswith("_var_"):
            raise ReservedAttributeError.format(
                class_name=cls.__name__,
                attr_name=attr_name,
                attr_type=type(value).__name__,
                attr_value=value,
            )

    @classmethod
    def __before_set__initialize_attr_as_context_var_descriptor(cls, attr_name, value):
        assert (
            attr_name not in cls._var_init_done_descriptors
        ), "This method should not be called when attribute is already initialized as ContextVar"

        if not cls._var_init_on_setattr:
            raise UndeclaredAttributeError.format(
                class_name=cls.__name__,
                attr_name=attr_name,
                attr_type=type(value).__name__,
            )

        cls.__init_class_attr_as_descriptor(attr_name)

    # collections.abc.MutableMapping implementation methods

    @classmethod
    def _asdict(cls) -> dict:
        out = {}
        for key, ctx_var in cls._var_init_done_descriptors.items():
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
        ctx_var = cls._var_init_done_descriptors[key]
        try:
            return ctx_var.get()
        except LookupError as err:
            raise KeyError(key) from err

    @classmethod
    def __setitem__(cls, key, value):
        ctx_var = cls.__before_set__ensure_initialized(key, value)
        ctx_var.set(value)

    def __delitem__(self, key):
        """Delete member of the registry (NOT IMPLEMENTED, ALWAYS THROWS ERROR).

        This method always throws :class:`contextvars_extras.descriptor.DeleteIsNotImplementedError`

        This is done because Python's context variables cannot be garbage-collected.
        Once a ``ContextVar`` object is created, it has to live forever.
        If you delete it, you get a memory leak.

        To avoid memory leaks, we have to completely ban deletion of context variables,
        and thus this method always throws an error.
        """
        ctx_var = self.__before_set__ensure_initialized(key, None)
        ctx_var.__delete__(self)


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
    """Can't set attribute: {class_name}.{attr_name} because of the special '_var_' prefix.

    This exception is raised when you try to set a special attribute::

        instance.{attr_name} = {attr_value!r}

    The ``_var_*`` prefix is reserved for configuration of the :class:`ContextVarRegistry`.
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
            _var_init_on_setattr = False

    Because of ``_var_init_on_setattr=False``, you can use only pre-defined variables.
    An attempt to set any other attribute will raise this exception.

    So, you have 3 options to solve the problem:

    1. Add attribute to the class, like this::

        class {class_name}(ContextVarsRegistry):
            {attr_name}: {attr_type}

    2. Enable dynamic initialization of new context variables, like this::

        class {class_name}(ContextVarsRegistry):
            _var_init_on_setattr = True

    3. Check the name of the attribute: '{attr_name}'.
       Maybe there is a typo in the name?
    """
