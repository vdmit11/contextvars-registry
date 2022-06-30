import abc
import threading
from contextlib import ExitStack
from contextvars import ContextVar
from types import FunctionType, MethodType
from typing import Any, ClassVar, Dict, Iterable, Iterator, MutableMapping, Tuple, get_type_hints

from sentinel_value import sentinel

from contextvars_extras.context_var_descriptor import ContextVarDescriptor
from contextvars_extras.context_var_ext import DELETED, NO_DEFAULT, ContextVarExt, Token
from contextvars_extras.internal_utils import ExceptionDocstringMixin


class ContextVarsRegistryMeta(abc.ABCMeta):
    """Metaclass for ContextVarsRegistry and its subclasses.

    It automatically adds empty __slots__ to all registry classes.

    This metaclass adds empty :ref:`slots` to :class:`ContextVarsRegistry` and all its subclasses,
    which means that you can't set any attributes on a registry instance.

    Why?
    Because a registry doesn't have any real attributes.
    It only acts as a proxy, forwarding operations to context variables
    (which are hosted in the registry class, not in the instance).

    Setting regular (non-context-variable) attributes on an instance would almost
    always lead to nasty race conditions (bugs that occur in production, but not in tests).

    To avoid that, we set ``__slots__ = tuple()`` for all registry classes,
    thus ensuring that all the state is stored in context variables.
    """

    def __new__(cls, name, bases, attrs):  # noqa: D102
        attrs.setdefault("__slots__", tuple())
        return super().__new__(cls, name, bases, attrs)


class ContextVarsRegistry(MutableMapping[str, Any], metaclass=ContextVarsRegistryMeta):
    """A collection of ContextVar() objects, with nice @property-like way to access them."""

    _registry_allocate_on_setattr: ClassVar[bool] = True
    """Automatically create new context variables when setting attributes?

    If set to True (default), missing ContextVar() objects are dynamically allocated when
    setting attributes. That is, you can define an empty class, and then set arbitrary attributes:

        >>> class CurrentVars(ContextVarsRegistry):
        ...    pass

        >>> current = CurrentVars()
        >>> current.locale = 'en'
        >>> current.timezone = 'UTC'

    However, if you find this behavior weak, you may disable it, like this:

        >>> class CurrentVars(ContextVarsRegistry):
        ...     _registry_allocate_on_setattr = False
        ...     locale: str = 'en'

        >>> current = CurrentVars()
        >>> current.timezone = 'UTC'
        AttributeError: ...
    """

    _registry_var_descriptors: ClassVar[Dict[str, ContextVarDescriptor]]
    """A dictionary of all context vars in the registry.

    Keys are attribute names, and values are instances of :class:`ContextVarDescriptor`.

    The dictionary can be mutated at run time, because new variables can be created on the fly.

    Actually, this dictionary isn't strictly required.
    You can derive this mapping by iterating over all class attributes and calling isinstance().
    It is just kept for the convenience, and maybe small performance improvements.
    """

    _registry_var_allocate_lock: ClassVar[threading.RLock]
    """A lock that protects against race conditions during cration of new ContextVar() objects.

    ContextVar() objects are lazily created on 1st attempt to set an attribute.
    So a race condition is possible: multiple concurrent threads (or co-routines)
    set an attribute for the 1st time, and thus create multiple ContextVar() objects.
    The last created ContextVar() object wins, and others are lost, causing a memory leak.

    So this lock is needed to ensure that ContextVar() object is created only once.
    """

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
        return _OverrideRegistryAttrsTemporarily(self, attr_names_and_values)

    def __init_subclass__(cls):
        cls.__ensure_subclassed_properly()
        cls._registry_var_descriptors = {}
        cls._registry_var_allocate_lock = threading.RLock()
        cls.__convert_attrs_to_var_descriptors()
        cls.__init_var_allocation_on_setattr()
        super().__init_subclass__()

    @classmethod
    def __ensure_subclassed_properly(cls):
        if ContextVarsRegistry not in cls.__bases__:
            raise RegistryInheritanceError

    @classmethod
    def __init_var_allocation_on_setattr(cls):
        if not cls._registry_allocate_on_setattr:
            return

        # When _registry_allocate_on_setattr=True, we extend class with extra __setattr__() method,
        # that dynamically allocates ContextVarDescriptor() object if attribute is missing.
        #
        # Yeah, but why not just define a usual __setattr__() method?
        # Why do we need to generate the method dynamically?
        #
        # For 2 reasons:
        #
        # 1. Better static code analysis: when mypy sees `def __setattr__` in a class,
        #    it skips checks for undefined attributes. So adding the method dynamically
        #    allows to fool mypy and thus have better type checking.
        #
        # 2. Better performance: native object.__setattr__ is faster than a Python method.
        #    The overhead is small, but may become noticeable if you set variables often.
        #    So we can avoid this overhead by NOT overriding the built-in __setattr__() method.
        __setattr__ = cls.__setattr__

        assert (
            __setattr__ is object.__setattr__
        ), "Customizing __setattr__() is not allowed (because then super() won't work correctly)"

        def _ContextVarsRegistry__setattr__(self, attr_name, value):
            if not hasattr(cls, attr_name):
                cls.__before_set__ensure_allocated(attr_name, value)
            __setattr__(self, attr_name, value)

        cls.__setattr__ = _ContextVarsRegistry__setattr__  # type: ignore[assignment]

    # There is a bug in Pylint that gives false-positive warnings for classmethods below.
    # So, I have to mask that warning completely and wait until the bug in Pylint is fied.
    # pylint: disable=unused-private-member

    @classmethod
    def __convert_attrs_to_var_descriptors(cls):
        for attr_name, type_hint, attr_value in _get_attr_type_hints_and_values(cls):
            # Skip already initialized descriptors.
            #
            # This is needed to be able to do just this:
            #    class CurrentVars(ContextVarsRegistry):
            #        timezone = ContextVarDesciptor(default="UTC")
            #
            # So here we adopt such already existing descriptors.
            if isinstance(attr_value, ContextVarDescriptor):
                cls._registry_var_descriptors[attr_name] = attr_value
                continue

            # For other attributes, we may convert them to ContextVarDescriptor
            # (the decision depends on the type hint or the attribute value).
            if cls.__should_convert_to_descriptor(attr_name, type_hint, attr_value):
                cls.__allocate_var_descriptor(attr_name)

    @staticmethod
    def __should_convert_to_descriptor(attr_name: str, type_hint: Any, attr_value: Any) -> bool:
        # Have type hint?
        # Then the decision is simple: convert all attributes that are not marked with ClassVar.
        if type_hint is not _NO_TYPE_HINT:
            return not _is_class_var(type_hint)

        # No type hint?
        # Then things become implicit and tricky...
        # Here we have to use some common sense to guess which values should become context vars.
        #
        # The rules, roughly, are:
        #  - skip __special__ attrs
        #  - skip methods
        #  - skip @property
        #  - convert all other objects to ContextVarDescriptor

        # Skip special attributes, like __doc__ and __module__
        if _is_special_attr(attr_name):
            return False

        # Skip methods, but except for lambdas.
        # Lambdas are converted to context variables,
        # because usually you want to use lambdas as values, not methods.
        if _is_method(attr_value) and not _is_lambda(attr_value):
            return False

        # Skip @property and other kinds of descriptors.
        # ...except for lambdas again, because lambdas are technically descriptors,
        # as they implement __get__() that converts lambda to an instance-bound method.
        if _is_descriptor(attr_value) and not _is_lambda(attr_value):
            return False

        return True

    @classmethod
    def __allocate_var_descriptor(cls, attr_name):
        with cls._registry_var_allocate_lock:
            assert attr_name not in cls._registry_var_descriptors

            value = getattr(cls, attr_name, NO_DEFAULT)
            assert not isinstance(value, (ContextVar, ContextVarExt, ContextVarDescriptor))

            descriptor: ContextVarDescriptor = ContextVarDescriptor(default=value)
            descriptor.__set_name__(cls, attr_name)
            setattr(cls, attr_name, descriptor)
            cls._registry_var_descriptors[attr_name] = descriptor

    def __init__(self):
        self.__ensure_subclassed_properly()
        super().__init__()

    @classmethod
    def __before_set__ensure_allocated(cls, attr_name, value) -> ContextVarDescriptor:
        try:
            return cls._registry_var_descriptors[attr_name]
        except KeyError:
            cls.__before_set__allocate_var_descriptor(attr_name, value)
            return cls._registry_var_descriptors[attr_name]

    @classmethod
    def __before_set__allocate_var_descriptor(cls, attr_name, value):
        assert cls._registry_allocate_on_setattr
        assert not hasattr(cls, attr_name)
        assert attr_name not in cls._registry_var_descriptors

        if _is_annotated_with_class_var(cls, attr_name):
            raise SetClassVarAttributeError.format(
                class_name=cls.__name__,
                attr_name=attr_name,
            )

        cls.__allocate_var_descriptor(attr_name)

    # collections.abc.MutableMapping implementation methods

    def __iter__(self) -> Iterator[str]:
        return (
            key
            for (key, ctx_var) in self._registry_var_descriptors.items()
            if ctx_var.is_set(on_default=True, on_deferred_default=False)
        )

    def __len__(self):
        return sum(1 for _ in self.__iter__())

    @classmethod
    def __getitem__(cls, key):
        ctx_var = cls._registry_var_descriptors[key]
        try:
            return ctx_var.get()
        except LookupError as err:
            raise KeyError(key) from err

    @classmethod
    def __setitem__(cls, key, value):
        ctx_var = cls.__before_set__ensure_allocated(key, value)
        ctx_var.set(value)

    def __delitem__(self, key):
        ctx_var = self.__before_set__ensure_allocated(key, None)

        if not ctx_var.is_gettable():
            raise KeyError(key)

        ctx_var.delete()


_NO_ATTR_VALUE = sentinel("_NO_VALUE")
_NO_TYPE_HINT = sentinel("_NO_TYPE_HINT")


def _get_attr_type_hints_and_values(cls: object) -> Iterable[Tuple[str, Any, Any]]:
    type_hints = get_type_hints(cls)
    cls_attrs = vars(cls)

    for attr_name, type_hint in type_hints.items():
        attr_value = cls_attrs.get(attr_name, _NO_ATTR_VALUE)
        yield (attr_name, type_hint, attr_value)

    for attr_name, attr_value in cls_attrs.items():
        if attr_name in type_hints:
            continue
        yield (attr_name, _NO_TYPE_HINT, attr_value)


def _is_annotated_with_class_var(cls: type, attr_name: str) -> bool:
    type_hints = get_type_hints(cls)
    return (attr_name in type_hints) and _is_class_var(type_hints[attr_name])


def _is_class_var(type_hint: object) -> bool:
    origin = getattr(type_hint, "__origin__", None)
    return origin is ClassVar


def _is_method(obj: object) -> bool:
    return isinstance(obj, (FunctionType, MethodType))


def _is_descriptor(obj: object) -> bool:
    return hasattr(obj, "__get__")


def _is_special_attr(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _is_lambda(obj: object) -> bool:
    return isinstance(obj, FunctionType) and (obj.__name__ == "<lambda>")


class _OverrideRegistryAttrsTemporarily(ExitStack):
    """Helper for :class:`ContextVarsRegistry` that implements ``with registry(var=value)`` feature.

    On ``__enter__``, it sets registry attributes to the new values.
    On ``__exit__``, it restores the old values (using features of the base :class:`ExitStack`).

    The base ``ExitStack`` class is used mostly because of its nice exception handling feature
    (on exit, it tries to reset as much attributes as possible, despite of exceptions being thrown).

    See documentation for :meth:`ContextVarsRegistry.__call__` for details about this feature.
    """

    registry: ContextVarsRegistry
    attr_names_and_values: Dict[str, Any]

    def __init__(self, registry: ContextVarsRegistry, attr_names_and_values: Dict[str, Any]):
        self.registry = registry
        self.attr_names_and_values = attr_names_and_values
        super().__init__()

    def __enter__(self):
        registry = self.registry
        registry_class = registry.__class__

        for attr_name, new_value in self.attr_names_and_values.items():
            # In case of ContextVarDescriptor, use its special set()/reset() methods.
            # Otherwise, call standard setattr()/delattr() that work with any kind of attributes.
            #
            # Why not just always use the standard attribute calls?
            # Because ContextVar.reset() implements a special behavior: it can restore a special
            # "unset" state of the ContextVar object, which is not achievable by setting attributes.
            # So I had to implement the special case for context variables here.
            descriptor = getattr(registry_class, attr_name, None)
            if isinstance(descriptor, ContextVarDescriptor):
                reset_token: Token = descriptor.set(new_value)
                self.callback(descriptor.reset, reset_token)  # will be called on __exit__
            else:
                old_value = getattr(registry, attr_name, _NO_ATTR_VALUE)
                setattr(registry, attr_name, new_value)
                if old_value is _NO_ATTR_VALUE:
                    self.callback(delattr, registry, attr_name)
                else:
                    self.callback(setattr, registry, attr_name, old_value)


def save_context_vars_registry(
    registry: ContextVarsRegistry,
) -> Dict[str, Any]:
    """Dump variables from ContextVarsRegistry as dict.

    The resulting dict can be used as argument to :func:`restore_context_vars_registry`.
    """
    # pylint: disable=protected-access
    return {
        key: descriptor.get_raw() for key, descriptor in registry._registry_var_descriptors.items()
    }


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
         like ``DELETED`` tokens, or lazy initializers.

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
    for key, descriptor in registry._registry_var_descriptors.items():
        descriptor.context_var.set(get_saved_value(key, DELETED))


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


class SetClassVarAttributeError(ExceptionDocstringMixin, AttributeError):
    """Can't set ClassVar: '{class_name}.{attr_name}'.

    This exception is raised when an attribute is declared as :data:`typing.ClassVar`,
    like this::

        class {class_name}(ContextVarsRegistry):
            {attr_name}: ClassVar[...]

    ...but you're trying to set it on instance level, as if it was a context variable.

    To solve the issue, you need to either:

    1. Remove ``ClassVar`` annotation (and thus convert the attribute to a context variable).

    2. Set the attribute off the class (not instance), like this::

          {class_name}.{attr_name} = ...
    """
