"""ContextVarDescriptor - extension for the built-in ContextVar that behaves like @property."""

from enum import Enum

from contextvars import ContextVar, Token
from typing import Any, Callable, Generic, Optional, Type, TypeVar, Union, overload

from contextvars_registry.context_management import bind_to_empty_context
from contextvars_registry.internal_utils import ExceptionDocstringMixin

# A value stored in the context variable.
_VarValueT = TypeVar("_VarValueT")

# a value returned by .get() when ContextVar has no value
_FallbackT = TypeVar("_FallbackT")

# ContextVarDescriptor or its subclass
_DescriptorT = TypeVar("_DescriptorT", bound="ContextVarDescriptor[Any]")

# descriptor's owner (an object that contains descriptor as attribute)
_OwnerT = TypeVar("_OwnerT")


class NoDefault(Enum):
    """Special sentinel object that means: "default value is not set".

    This special :data:`NO_DEFAULT` object may appear in a number of places:

     - :attr:`ContextVarDescriptor.default`
     - :meth:`ContextVarDescriptor.get`
     - :func:`get_context_var_default`
     - and some other places

    where it indicates the "default value is not set" case
    (which is different from ``default = None``).

    Example usage::

      >>> timezone_var = ContextVarDescriptor("timezone_var")
      >>> if timezone_var.default is NO_DEFAULT:
      ...     print("timezone_var has no default value")
      timezone_var has no default value
    """

    NO_DEFAULT = "NO_DEFAULT"


NO_DEFAULT = NoDefault.NO_DEFAULT
"""Special sentinel object that means "default value is not set"

see docs for: :class:`NoDefault`
"""


class DeletionMark(Enum):
    """Special sentinel object written into ContextVar when it is erased.

    Problem: in Python, it is not possible to erase a :class:`~contextvars.ContextVar` object.
    Once a variable is set, it cannot be unset.
    But, we still want to have the deletion feature.

    So, the solution is:

    1. When the value is deleted, write an instance of :class:`DeletionMark`
       into the context variable.
    2. When reading the variable, detect the deletion mark and act as if there was no value
       (this logic is implemented by the :meth:`~ContextVarDescriptor.get` method).

    But, a litlle trick is that there are 2 slightly different ways to erase the variable,
    so :class:`DeletionMark` has exactly 2 instances:

    :data:`contextvars_registry.context_var_descriptor.DELETED`
     - written by :meth:`~ContextVarDescriptor.delete` method
     - :meth:`~ContextVarDescriptor.get` throws :class:`LookupError`

    :data:`contextvars_registry.context_var_descriptor.RESET_TO_DEFAULT`
     - written by :meth:`~ContextVarDescriptor.reset_to_default` method
     - :meth:`~ContextVarDescriptor.get` returns a :attr:`~ContextVarDescriptor.default` value

    But, all this is an implementation detail of the :meth:`ContextVarDescriptor` class,
    and in most cases, you shouldn't care about these special objects.

    A case when you do care is the :meth:`~ContextVarDescriptor.get_raw` method,
    that may return a special deletion mark. Here is how you handle it::

        >>> from contextvars_registry.context_var_descriptor import DELETED, RESET_TO_DEFAULT

        >>> timezone_var = ContextVarDescriptor("timezone_var", default="UTC")

        >>> timezone_var.delete()

        >>> value = timezone_var.get_raw()
        >>> if isinstance(value, DeletionMark):
        ...     print("timezone_var value was deleted")
        timezone_var value was deleted

    But again, in most cases, you shouldn't care about it.
    Just use the :meth:`ContextVarDescriptor.get` method, that will handle it for you.
    """

    DELETED = "DELETED"
    RESET_TO_DEFAULT = "RESET_TO_DEFAULT"


DELETED = DeletionMark.DELETED
"""Special object, written to ContextVar when its value is deleted.

see docs in: :class:`DeletionMark`.
"""

RESET_TO_DEFAULT = DeletionMark.RESET_TO_DEFAULT
"""Special object, written to ContextVar when it is reset to default.

see docs in: :class:`DeletionMark`
"""


class ContextVarDescriptor(Generic[_VarValueT]):
    context_var: ContextVar[Union[_VarValueT, DeletionMark]]
    """Reference to the underlying :class:`contextvars.ContextVar` object."""

    name: str
    """Name of the context variable.

    Equal to :attr:`contextvars.ContextVar.name`.

    Needed mostly for debugging and introspection purposes.

    Technically it may be any arbitrary string, of any length, and any format.
    However, it would be nice if in your code you make it equal to Python variable name, like this::

        >>> my_variable = ContextVarDescriptor(name="my_variable")

    or, even better, a fully qualified name::

        >>> my_variable = ContextVarDescriptor(name=(__name__ + '.' + 'my_variable'))

    That will help you later with debugging.

    .. Note::

       This attribute is read-only.

       It can only be set when the object is created (via :meth:`__init__` parameters).

       Although technically this attribute is writable (for performance purposes),
       setting it has no effect, and may cause bugs. So don't try to set it.
    """

    default: Union[_VarValueT, NoDefault]
    """Default value of the context variable.

    Returned by :meth:`get` if the variable is not bound to any value.

    If there is no default value, then this attribute is set to :data:`NO_DEFAULT` - a special
    sentinel object that indicates absence of any default value.

    .. Note::

       This attribute is read-only.

       It can only be set when the object is created (via :meth:`__init__` parameters).

       Although technically this attribute is writable (for performance purposes),
       setting it has no effect, and may cause bugs. So don't try to set it.
    """

    deferred_default: Optional[Callable[[], _VarValueT]]
    """A function, that produces a default value.

    Triggered by the :meth:`get` method (if the variable is not set),
    and once called, the result is written into the context variable
    (kind of lazy initialization of the context variable).

    .. Note::

       This attribute is read-only.

       It can only be set when the object is created (via :meth:`__init__` parameters).

       Although technically this attribute is writable (for performance purposes),
       setting it has no effect, and may cause bugs. So don't try to set it.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        default: Union[_VarValueT, NoDefault] = NO_DEFAULT,
        deferred_default: Optional[Callable[[], _VarValueT]] = None,
        _context_var: Optional[ContextVar[_VarValueT]] = None,
    ) -> None:
        """Initialize ContextVarDescriptor object.

        :param name: Variable name. Needed for introspection and debugging purposes.
                     Usually you don't want to set it manually, because it is automatically
                     formatted from owner class/attribute names.

        :param default: A default value, returned by the :meth:`get` method
                        if the variable is not bound to a value.
                        If default is missing, then :meth:`get` raises :class:`LookupError`.

        :param deferred_default: A function that produces a default value.
                                 Called by :meth:`get` method, once per context.
                                 That is, if you spawn 10 threads, then :attr:`deferred_default`
                                 is called 10 times, and you get 10 thread-local values.

        :param _context_var: A reference to an existing :class:`contextvars.ContextVar` object.
                             This parameter is for internal purposes, and you shouldn't use it.
                             Instead, use :meth:`ContextVarDescriptor.from_existing_var` constructor.
        """
        if not name:
            # postpone init until __set_name__() method is called
            self._postponed_init_args = (default, deferred_default, _context_var)
            return

        self._init(name, default, deferred_default, _context_var)

    def __set_name__(self, owner_cls: type, owner_attr_name: str) -> None:
        if hasattr(self, "_postponed_init_args"):
            name = f"{owner_cls.__module__}.{owner_cls.__name__}.{owner_attr_name}"
            self._init(name, *self._postponed_init_args)

    @classmethod
    def from_existing_var(
        cls: Type[_DescriptorT],
        context_var: ContextVar[_VarValueT],
        deferred_default: Optional[Callable[[], _VarValueT]] = None,
    ) -> "ContextVarDescriptor[_VarValueT]":
        """Create ContextVarDescriptor from an existing ContextVar object.

        Normally, when you instanciate :class:`ContextVarDescriptor`, its default constructor
        automatically creates a new :class:`~contextvars.ContextVar` object.
        This may not always be what you want.

        So this :meth:`ContextVarDescriptor.from_existing_var` is an alternative constructor
        that allows to cancel that automatic creation behavior, and instead use an existing
        :class:`~contextvars.ContextVar` object.

        Example::

            >>> timezone_var = ContextVar("timezone_var", default="UTC")
            >>> timezone_var_ext = ContextVarDescriptor.from_existing_var(timezone_var)

            >>> timezone_var_ext.name
            'timezone_var'

            >>> timezone_var_ext.get()
            'UTC'

            >>> timezone_var_ext.context_var is timezone_var
            True

        See also: :meth:`__init__` method documentation,
        where you can find description of the ``deferred_default`` and maybe other paramters.
        """
        name = context_var.name
        default = get_context_var_default(context_var)
        return cls(name, default, deferred_default, context_var)

    def _init(
        self,
        name: Optional[str],
        default: Union[_VarValueT, NoDefault],
        deferred_default: Optional[Callable[[], _VarValueT]],
        _context_var: Optional[ContextVar[_VarValueT]],
    ) -> None:
        assert name
        assert not ((default is not NO_DEFAULT) and (deferred_default is not None))

        if _context_var is None:
            _context_var = _new_context_var(name, default)

        self.context_var = _context_var  # type: ignore[assignment]
        self.name = name
        self.default = default
        self.deferred_default = deferred_default

        self._init_fast_methods()
        self._init_deferred_default()

    def _init_fast_methods(self) -> None:
        # Problem: basic ContextVar.get()/.set()/etc() must have good performance.
        #
        # So, I decided to do some evil premature optimization: instead of regular methods,
        # I define them as functions (closures) here, and then write them as methods to
        # the ContextVarDescriptor() instance.
        #
        # Closures, are faster than methods, because they can:
        #  - take less arguments (each function argument adds some overhead)
        #  - avoid `self` (because Python's attribute resolution mechanism has some performance hit)
        #  - avoid `.` - the dot operator (because, again, attribute access is slow)
        #  - avoid globals (because they're slower than local variables)
        #
        # Of course, all these overheads are minor, but they add up.
        # For example .get() call became 2x faster after these optimizations.
        # So I decided to keep them.

        # The `.` (the dot operator that resoles attributes) has some overhead.
        # So, do it in advance to avoid dots in closures below.
        context_var = self.context_var
        context_var_get = context_var.get
        context_var_set = context_var.set
        context_var_ext_default = self.default
        context_var_ext_deferred_default = self.deferred_default

        context_var_ext_default_is_set = context_var_ext_default is not NO_DEFAULT
        context_var_ext_deferred_default_is_set = context_var_ext_deferred_default is not None

        # Local variables are faster than globals.
        # So, copy all needed globals and thus make them locals.
        __NOT_SET = _NOT_SET
        _NO_DEFAULT = NO_DEFAULT
        _DELETED = DELETED
        _RESET_TO_DEFAULT = RESET_TO_DEFAULT
        _LookupError = LookupError

        # Ok, now define closures that use all the variables prepared above.

        # NOTE: function name is chosen such that it looks good in stack traces.
        # When an exception is thrown, just "get" looks cryptic, while "_method_ContextVarDescriptor_get"
        # at least gives you a hint that the ContextVarDescriptor.get method is the source of exception.
        def _method_ContextVarDescriptor_get(default=NO_DEFAULT):
            if default is _NO_DEFAULT:
                value = context_var_get()
            else:
                value = context_var_get(default)

            # special sentinel object, left by ContextVarDescriptor.delete()
            if value is _DELETED:
                if default is not _NO_DEFAULT:
                    return default
                raise _LookupError(context_var)

            # special sentinel object, left by ContextVarDescriptor.reset_to_default()
            if value is _RESET_TO_DEFAULT:
                if default is not _NO_DEFAULT:
                    return default
                if context_var_ext_default is not _NO_DEFAULT:
                    return context_var_ext_default
                if context_var_ext_deferred_default is not None:
                    value = context_var_ext_deferred_default()
                    context_var_set(value)
                    return value
                raise _LookupError(context_var)

            return value

        self.get = _method_ContextVarDescriptor_get  # type: ignore[method-assign]

        def _method_ContextVarDescriptor_is_set(on_default=False, on_deferred_default=False):
            value = context_var_get(__NOT_SET)

            if (value is __NOT_SET) or (value is _RESET_TO_DEFAULT):
                if context_var_ext_default_is_set:
                    return on_default
                if context_var_ext_deferred_default_is_set:
                    return on_deferred_default
                return False

            return value is not _DELETED

        self.is_set = _method_ContextVarDescriptor_is_set  # type: ignore[method-assign]

        # Copy some methods from ContextVar.
        # These are even better than closures above, because they are C functions.
        # So by calling, for example ``ContextVarRegistry.set()``, you're *actually* calling
        # tje low-level C function ``ContextVar.set`` directly, without any Python-level wrappers.
        self.get_raw = self.context_var.get  # type: ignore[assignment]
        self.set = self.context_var.set  # type: ignore[assignment]
        self.reset = self.context_var.reset  # type: ignore[assignment]

    def _init_deferred_default(self) -> None:
        # In case ``deferred_default`` is used, put a special marker object to the variable
        # (otherwise ContextVar.get() method will not find any value and raise a LookupError)
        if self.deferred_default and not self.is_set():
            self.reset_to_default()

    @overload
    def get(self) -> _VarValueT: ...

    @overload
    def get(self, default: _FallbackT) -> Union[_VarValueT, _FallbackT]: ...

    def get(self, default=NO_DEFAULT):
        """Return a value for the context variable for the current context.

        If there is no value for the variable in the current context,
        the method will:

          * return the value of the ``default`` argument of the method, if provided; or
          * return the :attr:`default` value for the variable, if it was created with one; or
          * return a value produced by the :attr:`deferred_default` function; or
          * raise a :exc:`LookupError`.

        Example usage::

            >>> locale_var = ContextVarDescriptor('locale_var', default='UTC')

            >>> locale_var.get()
            'UTC'

            >>> locale_var.set('Europe/London')
            <Token ...>

            >>> locale_var.get()
            'Europe/London'


        Note that if that if there is no ``default`` value, the method raises :data:`LookupError`::

            >>> locale_var = ContextVarDescriptor('locale_var')

            >>> try:
            ...     locale_var.get()
            ... except LookupError:
            ...     print('LookupError was raised')
            LookupError was raised

            # The exception can be prevented by supplying the `.get(default)` argument.
            >>> locale_var.get(default='en')
            'en'

            >>> locale_var.set('en_GB')
            <Token ...>

            # The `.get(default=...)` argument is ignored since the value was set above.
            >>> locale_var.get(default='en')
            'en_GB'
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_init_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    @overload
    def get_raw(self) -> Union[_VarValueT, DeletionMark]: ...
    @overload
    def get_raw(self, default: _FallbackT) -> Union[_VarValueT, _FallbackT, DeletionMark]: ...

    def get_raw(self, default=NO_DEFAULT):
        """Return a value for the context variable, without overhead added by :meth:`get` method.

        This is a more lightweight version of :meth:`get` method.
        It is faster, but doesn't support some features (like deletion).

        In fact, it is a direct reference to the standard :meth:`contextvars.ContextVar.get` method,
        which is a built-in method (written in C), check this out::

            >>> timezone_var = ContextVarDescriptor('timezone_var')

            >>> timezone_var.get_raw
            <built-in method get of ...ContextVar object ...>

            >>> timezone_var.get_raw == timezone_var.context_var.get
            True

        So here is absolutely no overhead on top of the standard :meth:`contextvars.ContextVar.get`,
        and you can safely use this :meth:`get_raw` method when you need performance.

        .. Note::

           This method is a direct shortcut to the built-in method, see also its documentation:
           :meth:`contextvars.ContextVar.get`
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_init_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def is_gettable(self) -> bool:
        """Check if the method :meth:`.get()` would throw an exception.

        :returns:
          - ``True`` if :meth:`get` would return a value.
          - ``False`` if :meth:`get` would raise :class:`LookupError`.

        Examples::

            # An empty variable without a default value is not gettable.
            # (because an attempt to call .get() would throw a LookupError)
            >>> timezone_var = ContextVarDescriptor("timezone_var")
            >>> timezone_var.is_gettable()
            False

            # But a variable with the default value is instantly gettable.
            >>> timezone_var = ContextVarDescriptor("timezone_var", default="UTC")
            >>> timezone_var.is_gettable()
            True

            # ...and that also works with defferred defaults.
            >>> timezone_var = ContextVarDescriptor("timezone_var", deferred_default=lambda: "UTC")
            >>> timezone_var.is_gettable()
            True

            # Once you call delete(), the variable is not gettable anymore.
            >>> timezone_var.delete()
            >>> timezone_var.is_gettable()
            False

            # ...but a call to .reset_to_default() again puts it to a state,
            # where .get() returns a default value, so it becomes "gettable" again
            >>> timezone_var.reset_to_default()
            >>> timezone_var.is_gettable()
            True
        """
        return self.is_set(on_default=True, on_deferred_default=True)

    def is_set(self, on_default: bool = False, on_deferred_default: bool = False) -> bool:
        """Check if the context variable is set.

        We say that a context variable is set if the :meth:`set` was called,
        and until that point, the variable is not set, even if it has a default value,
        check this out::

            # Initially, the variable is not set (even with a default value)
            >>> timezone_var = ContextVarDescriptor('timezone_var', default='UTC')
            >>> timezone_var.is_set()
            False

            # Once .set() is called, the .is_set() method returns True.
            >>> timezone_var.set('GMT')
            <Token ...>
            >>> timezone_var.is_set()
            True

            # .reset_to_default() also "un-sets" the variable
            >>> timezone_var.reset_to_default()
            >>> timezone_var.is_set()
            False

        This may seem odd, but this is how the standard :meth:`contextvars.ContextVar.get` method
        treats default values, check this out::

            # The .get() method treats variable as not set and returns a fallback value.
            # The trick is that default "UTC" is not an initial value of the variable,
            # but rather a default argument for the .get() method below.
            >>> timezone_var.get("<MISSING>")
            '<MISSING>'

        So, here in the :meth:`is_set` method we're implementing the same behavior: we say that
        initially a variable is not set (even if it has a default value), and becomes set
        after you call the :meth:`set` method.

        But, if you want to tune this behavior and take into account default values,
        then you can do it via parameters::

            >>> timezone_var.is_set(on_default=True, on_deferred_default=True)
            True

        or, just use :meth:`is_gettable` (same as above, but shorter)::

            >>> timezone_var.is_gettable()
            True
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_init_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def set(self, value: _VarValueT) -> "Token[_VarValueT]":
        """Call to set a new value for the context variable in the current context.

        The required ``value`` argument is the new value for the context variable.

        :returns: a :class:`~contextvars.Token` object that can be passed
                  to :meth:`reset` method to restore the variable to its previous value.

        .. Note::

           This method is a direct shortcut to the built-in method, see also its documentation:
           :meth:`contextvars.ContextVar.set`
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_init_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def set_if_not_set(self, value: _VarValueT) -> _VarValueT:
        """Set value if not yet set.

        The behavior is akin to Python's :meth:`dict.setdefault` method:

        - If the variable is not yet set, then set it, and return the new value
        - If the variable is already set, then don't overwrite it, and return the existing value

        That is, it always returns what is stored in the context variable
        (which is not the same as the input ``value`` argument).

        Examples::

            >>> locale_var = ContextVarDescriptor('locale_var', default='en')

            # The context variable has no value set yet (the `default='en'` above isn't
            # treated as if value was set), so the call to .set_if_not_set() has effect.
            >>> locale_var.set_if_not_set('en_US')
            'en_US'

            # The 2nd call to .set_if_not_set() has no effect.
            >>> locale_var.set_if_not_set('en_GB')
            'en_US'

            >>> locale_var.get(default='en')
            'en_US'

            # .delete() method reverts context variable into "not set" state.
            >>> locale_var.delete()
            >>> locale_var.set_if_not_set('en_GB')
            'en_GB'

            # .reset_to_default() also means that variable becomes "not set".
            >>> locale_var.reset_to_default()
            >>> locale_var.set_if_not_set('en_AU')
            'en_AU'
        """
        existing_value = self.get(_NOT_SET)

        if existing_value is _NOT_SET:
            self.set(value)
            return value

        return existing_value

    def reset(self, token: "Token[_VarValueT]") -> None:
        """Reset the context variable to a previous value.

        :param token: A :class:`~contextvars.Token` object returned by :meth:`set` method.

        After the call, the variable is restored to whatever state it had before the :meth:`set`
        method was called. That works even if the variable was previously not set::

            >>> locale_var = ContextVar('locale_var')

            >>> token = locale_var.set('new value')
            >>> locale_var.get()
            'new value'

            # After the .reset() call, the var has no value again,
            # so locale_var.get() would raise a LookupError.
            >>> locale_var.reset(token)
            >>> locale_var.get()
            Traceback (most recent call last):
            ...
            LookupError: ...

        .. Note::

           This method is a direct shortcut to the built-in method, see also its documentation:
           :meth:`contextvars.ContextVar.reset`
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_init_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def reset_to_default(self) -> None:
        """Reset context variable to its default value.

        Example::

            >>> timezone_var = ContextVarDescriptor('timezone_var', default='UTC')

            >>> timezone_var.set('Antarctica/Troll')
            <Token ...>

            >>> timezone_var.reset_to_default()

            >>> timezone_var.get()
            'UTC'

        When there is no :attr:`default`, then :meth:`reset_to_default` has
        the same effect as :meth:`delete`::

            >>> timezone_var = ContextVarDescriptor('timezone_var')

            >>> timezone_var.set('Antarctica/Troll')
            <Token ...>

            >>> timezone_var.reset_to_default()

            # timezone_var has no default value, so .get() call raises LookupError.
            >>> try:
            ...     timezone_var.get()
            ... except LookupError:
            ...     print('LookupError was raised')
            LookupError was raised

            # The exception can be avoided by passing a `default=...` value.
            timezone_var.get(default='UTC')
            'UTC'
        """
        self.set(RESET_TO_DEFAULT)  # type: ignore[arg-type]

    def delete(self) -> None:
        """Delete value stored in the context variable.

        Example::

            # Create a context variable, and set a value.
            >>> timezone_var = ContextVarDescriptor('timezone_var')
            >>> timezone_var.set('Europe/London')
            <Token ...>

            # ...so .get() call doesn't raise an exception and returns the value
            >>> timezone_var.get()
            'Europe/London'

            # Call .delete() to erase the value.
            >>> timezone_var.delete()

            # Once value is deleted, the .get() method raises LookupError.
            >>> try:
            ...     timezone_var.get()
            ... except LookupError:
            ...     print('LookupError was raised')
            LookupError was raised

            # The exception can be avoided by passing a `default=...` value.
            >>> timezone_var.get(default='GMT')
            'GMT'

        .. Note::

           :meth:`delete` does NOT reset the variable to its :attr:`default` value.

           There is a special method for that purpose: :meth:`reset_to_default`
        """
        self.set(DELETED)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"

    # Python descriptor protocol implementation

    @overload
    def __get__(
        self: _DescriptorT, owner_instance: None, owner_cls: Type[_OwnerT]
    ) -> _DescriptorT: ...

    @overload
    def __get__(self, owner_instance: _OwnerT, owner_cls: Type[_OwnerT]) -> _VarValueT: ...

    @overload
    def __get__(
        self: _DescriptorT, owner_instance: Any, owner_cls: Any
    ) -> Union[_DescriptorT, _VarValueT]: ...

    def __get__(self, owner_instance, owner_cls):
        if owner_instance is None:
            return self
        try:
            return self.get()
        except LookupError as err:
            raise ContextVarNotSetError.format(context_var_name=self.name) from err

    def __set__(
        self,
        owner_instance: "Type[ContextVarDescriptor[_VarValueT]]",
        value: _VarValueT,
    ) -> None:
        assert owner_instance is not None
        self.set(value)

    def __delete__(self, owner_instance: "Type[ContextVarDescriptor[_VarValueT]]") -> None:
        self.__get__(owner_instance, None)  # needed to raise AttributeError if already deleted
        self.delete()


# A special sentinel object, used internally by methods like .is_set() and .set_if_not_set()
class _NotSet(Enum):
    NOT_SET = "NOT_SET"


_NOT_SET = _NotSet.NOT_SET


def _new_context_var(
    name: str,
    default: Union[_VarValueT, NoDefault],
) -> ContextVar[Union[_VarValueT]]:
    context_var: ContextVar[_VarValueT]

    if isinstance(default, NoDefault):
        context_var = ContextVar(name)
    else:
        context_var = ContextVar(name, default=default)

    return context_var


@overload
def get_context_var_default(
    context_var: ContextVar[_VarValueT],
) -> Union[_VarValueT, NoDefault]: ...


@overload
def get_context_var_default(
    context_var: ContextVar[_VarValueT],
    missing: _FallbackT,
) -> Union[_VarValueT, _FallbackT]: ...


@bind_to_empty_context
def get_context_var_default(
    context_var: ContextVar[_VarValueT],
    missing: Union[_FallbackT, NoDefault] = NO_DEFAULT,
) -> Union[_VarValueT, _FallbackT, NoDefault]:
    """Get a default value from :class:`contextvars.ContextVar` object.

    Example::

      >>> from contextvars import ContextVar
      >>> from contextvars_registry.context_var_descriptor import get_context_var_default

      >>> timezone_var = ContextVar('timezone_var', default='UTC')

      >>> timezone_var.set('GMT')
      <Token ...>

      >>> get_context_var_default(timezone_var)
      'UTC'

    In case the default value is missing, the :func:`get_context_var_default`
    returns a special sentinel object called :data:`NO_DEFAULT`::

      >>> timezone_var = ContextVar('timezone_var')  # no default value

      >>> timezone_var.set('UTC')
      <Token ...>

      >>> get_context_var_default(timezone_var)
      <NoDefault.NO_DEFAULT: 'NO_DEFAULT'>

    You can also use a custom missing marker (instead of :data:`NO_DEFAULT`), like this::

      >>> get_context_var_default(timezone_var, '[NO DEFAULT TIMEZONE]')
      '[NO DEFAULT TIMEZONE]'
    """
    try:
        return context_var.get()
    except LookupError:
        return missing


class ContextVarNotSetError(ExceptionDocstringMixin, AttributeError, LookupError):
    """Context variable is not set: '{context_var_name}'.

    This exception is usually raised when you declare a context variable without a default value,
    like this:

        >>> from contextvars_registry import ContextVarsRegistry
        >>> class Current(ContextVarsRegistry):
        ...     timezone: str
        >>> current = Current()

    In this case, the variable remains unitialized (as if the attribute was never set),
    so an attempt to read the attribute will raise an exception::

        >>> current.timezone
        Traceback (most recent call last):
        ...
        contextvars_registry.context_var_descriptor.ContextVarNotSetError: ...

    So you have 2 options to solve the problem:

    1. Execute your code with setting the missing attribute, like this:

        >>> with current(timezone='UTC'):
        ...     # put your code here
        ...     print(current.timezone)  # now it doesn't raise the error
        UTC

    2. Add a default value to your registry class, like this::

        >>> class Current(ContextVarsRegistry):
        ...     timezone: str = 'UTC'
        >>> current = Current()
        >>> current.timezone
        'UTC'

    .. Note::

      This exception is a subclass of **both** ``AttributeError`` and ``LookupError``.

      - ``AttributeError`` comes from Python's descriptor protocol.
        We have to throw it, otherwise ``hasattr()`` and ``geattr()`` will not work nicely.

      - ``LookupError`` is thrown by the standard ``contextvars.ContextVar.get()`` method
        when the variable is not set. So we do the same for consistency with the standard library.

      So, to fit both cases, this exception uses both ``AttributeErrror`` and ``LookupError``
      as base classes.
    """
