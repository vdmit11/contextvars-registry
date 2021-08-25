from contextvars import ContextVar, Token
from typing import Any, Callable, Optional

from contextvars_extras.util import ExceptionDocstringMixin, Missing, Sentinel

# A special sentinel object that we put into ContextVar when you delete a value from it
# (when ContextVarDescriptor.delete() method is called).
ContextVarValueDeleted = Sentinel(__name__, "ContextVarValueDeleted")

# Another special marker that we put into ContextVar when it is not yet initialized,
# used in 2 cases:
#  1. when ContextVarDescriptor(deferred_default=...) argument is used
#  2. when ContextVarDescriptor.reset_to_default() method is called
ContextVarNotInitialized = Sentinel(__name__, "ContextVarNotInitialized")

# A no-argument function that produces a default value for ContextVarDescriptor
DeferredDefaultFn = Callable[[], Any]


class ContextVarDescriptor:
    """A ``ContextVar`` wrapper that behaves like ``@property`` when attached to a class.

    This thing is designed to be placed in as class attribute, like this::

        >>> class MyVars:
        ...     locale = ContextVarDescriptor(default='en')
        >>> my_vars = MyVars()

    and it provides ``@property``-like access to the context variable.

    That is, you just get/set object attributes, and under the hood it calls methods of
    the underlying ``ContextVar`` object::

        >>> my_vars.locale
        'en'
        >>> my_vars.locale = 'en_US'
        >>> my_vars.locale
        'en_US'

    The underlying :class:`contextvars.ContextVar` methods can be reached via class attributes::

        >>> MyVars.locale.get()
        'en_US'
        >>> token = MyVars.locale.set('en_GB')
        >>> MyVars.locale.get()
        'en_GB'
        >>> MyVars.locale.reset(token)
        >>> MyVars.locale.get()
        'en_US'
    """

    context_var: ContextVar
    name: str
    _default: Any
    _deferred_default: Optional[DeferredDefaultFn]

    def __init__(
        self,
        name: Optional[str] = None,
        default: Optional[Any] = Missing,
        deferred_default: Optional[DeferredDefaultFn] = None,
        owner_cls: Optional[type] = None,
        owner_attr: Optional[str] = None,
        context_var: Optional[ContextVar] = None,
    ):
        """Initialize ContextVarDescriptor object.

        :param name: Name for the underlying ``ContextVar`` object.
                     Needed for introspection and debugging purposes.
                     Ususlly you don't want to set it manually, because it is automatically
                     formatted from owner class/attribute names.

        :param default: The default value for the  underlying ``ContextVar`` object.
                        Returned by the ``get()`` method if the variable is not bound to a value.
                        If default is missing, then ``get()`` may raise ``LookupError``.

        :param deferred_default: A function that produces a default value.
                                 Called by ``get()`` method, once per context.
                                 That is, if you spawn 10 threads, then ``deferred_default()``
                                 is called 10 times, and you get 10 thread-local values.

        :param owner_cls: Reference to a class, where the descritor is placed.
                          Usually it is captured automatically by the ``__set_name__`` method,
                          however, you need to pass it manually if you're adding a new descriptor
                          after the class is already created.

        :param owner_attr: Name of the attribute, where the descriptor is placed.
                           Usually it is captured automatically by the ``__set_name__`` method,
                           however, you need to pass it manually if you're adding a new descriptor
                           after the class is already creted.

        :param context_var: A reference to an existing ``ContextVar`` object.
                            You need it only if you want to re-use an existing object.
                            If missing, a new ``ContextVar`` object is created automatically.

        There are 4 ways to initialize a ``ContextVarsDescriptor`` object:

        1. Most common way - inside class body::

             >>> class Vars:
             ...     timezone = ContextVarDescriptor(default='UTC')

             >>> Vars.timezone.name
             'contextvars_extras.descriptor.Vars.timezone'

           In this case, the owner class/attribute is captured automatically by the standard
           :meth:`__set_name__` method (called automatically by Python when the class is created).

           So a new ``ContextVar`` object is created automatically in the ``__set_name__`` method,
           and its name is composed from class/attribute names.

           This is the easiest way to initialize ``ContextVarDescriptor`` objects, and in most
           cases, you probably want to use it. However, if you create descriptors outside of the
           class body, you need to use one of alternative ways...

        2. Manually pass ``owner_cls`` and ``owner_attr`` arguments::

            >>> class Vars:
            ...    pass
            >>> Vars.timezone = ContextVarDescriptor(owner_cls=Vars, owner_attr='timezone')

            >>> Vars.timezone.name
            'contextvars_extras.descriptor.Vars.timezone'

        3. Set a completely custom name::

            >>> timezone_descriptor = ContextVarDescriptor(name='timezone_context_var')

            >>> timezone_descriptor.context_var.name
            'timezone_context_var'

        4. Re-use an existing ``ContextVar`` object::

            >>> timezone_context_var = ContextVar('timezone_context_var')
            >>> timezone_descriptor = ContextVarDescriptor(context_var=timezone_context_var)

            >>> timezone_descriptor.context_var is timezone_context_var
            True
        """
        assert not ((default is not Missing) and (deferred_default is not None))
        self._default = default
        self._deferred_default = deferred_default

        if context_var:
            assert not name and not default
            self._set_context_var(context_var)
        elif name:
            context_var = self._new_context_var(name, default)
            self._set_context_var(context_var)
        elif owner_cls and owner_attr:
            context_var = self._new_context_var_for_owner(owner_cls, owner_attr, default)
            self._set_context_var(context_var)

    def __set_name__(self, owner_cls: type, owner_attr: str):
        if hasattr(self, "context_var"):
            return

        context_var = self._new_context_var_for_owner(owner_cls, owner_attr, self._default)
        self._set_context_var(context_var)

    @classmethod
    def _new_context_var(cls, name: str, default: Any) -> ContextVar:
        context_var: ContextVar

        if default is Missing:
            context_var = ContextVar(name)
        else:
            context_var = ContextVar(name, default=default)

        return context_var

    @classmethod
    def _new_context_var_for_owner(cls, owner_cls: type, owner_attr: str, default) -> ContextVar:
        name = f"{owner_cls.__module__}.{owner_cls.__name__}.{owner_attr}"
        return cls._new_context_var(name, default)

    def _set_context_var(self, context_var: ContextVar):
        assert not hasattr(self, "context_var")

        # In case ``deferred_default`` is used, put a special marker object to the variable
        # (otherwise ContextVar.get() method will not find any value and raise a LookupError)
        if self._deferred_default:
            context_var_is_not_initialized = context_var.get(Missing) == Missing
            if context_var_is_not_initialized:
                context_var.set(ContextVarNotInitialized)

        self.context_var = context_var
        self.name = context_var.name

        self._initialize_fast_methods()

    def _initialize_fast_methods(self):
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
        descriptor_default = self._default
        descriptor_deferred_default = self._deferred_default

        # Local variables are faster than globals.
        # So, copy all needed globals and thus make them locals.
        _Missing = Missing
        _ContextVarValueDeleted = ContextVarValueDeleted
        _ContextVarNotInitialized = ContextVarNotInitialized
        _LookupError = LookupError

        # Ok, now define closures that use all the variables prepared above.

        # -> ContextVarDescriptor.get
        def get(default=_Missing):
            if default is _Missing:
                value = context_var_get()
            else:
                value = context_var_get(default)

            # special marker, left by ContextVarDescriptor.reset_to_default()
            if value is _ContextVarNotInitialized:
                if default is not _Missing:
                    return default
                if descriptor_default is not _Missing:
                    return descriptor_default
                if descriptor_deferred_default is not None:
                    value = descriptor_deferred_default()
                    context_var_set(value)
                    return value
                raise _LookupError(context_var)

            # special marker, left by ContextVarDescriptor.delete()
            if value is _ContextVarValueDeleted:
                if default is not _Missing:
                    return default
                raise _LookupError(context_var)

            return value

        self.get = get

        # -> ContextVarDescriptor.is_set
        def is_set() -> bool:
            return context_var_get(_Missing) not in (
                _Missing,
                _ContextVarValueDeleted,
                _ContextVarNotInitialized,
            )

        self.is_set = is_set

        # -> ContextVarDescriptor.set_if_not_set
        def set_if_not_set(new_value) -> Any:
            existing_value = context_var_get(_Missing)

            if existing_value in (_Missing, _ContextVarValueDeleted, ContextVarNotInitialized):
                context_var_set(new_value)
                return new_value

            return existing_value

        self.set_if_not_set = set_if_not_set

        # -> ContextVarDescriptor.reset_to_default
        def reset_to_default():
            context_var_set(_ContextVarNotInitialized)

        self.reset_to_default = reset_to_default

        # -> ContextVarDescriptor.delete
        def delete():
            context_var_set(_ContextVarValueDeleted)

        self.delete = delete

        # Copy some methods from ContextVar.
        # These are even better than closures above, because they are C functions.
        # So by calling, for example ``ContextVarRegistry.set()``, you're *actually* calling
        # tje low-level C function ``ContextVar.set`` directly, without any Python-level wrappers.
        self.get_raw = self.context_var.get
        self.set = self.context_var.set
        self.reset = self.context_var.reset

    def get(self, default=Missing):
        """Return a value for the context variable for the current context.

        If there is no value for the variable in the current context,
        the method will:

          * return the value of the ``default`` argument of the method, if provided; or
          * return the default value for the context variable, if it was created with one; or
          * raise a :exc:`LookupError`.

        Example usage::

            >>> locale_var = ContextVarDescriptor('locale_var', default='UTC')

            >>> locale_var.get()
            'UTC'

            >>> locale_var.set('Europe/London')
            <Token ...>

            >>> locale_var.get()
            'Europe/London'


        Note that if that if there is no ``default`` value, it may raise ``LookupError``::

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
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def get_raw(self, default=Missing):
        """Return a value for the context variable, without overhead added by :meth:`get` method.

        This is a more lightweight version of :meth:`get` method.
        It is faster, but doesn't support some features (like deletion).

        In fact, it is a direct reference to the standard :meth:`contextvars.ContextVar.get` method,
        which is a built-in method (written in C), check this out::

            >>> timezone_var = ContextVarDescriptor('timezone_var')

            >>> timezone_var.get_raw
            <built-in method get of ContextVar object ...>

            >>> timezone_var.get_raw == timezone_var.context_var.get
            True

        So here is absolutely no overhead on top of the standard ``ContextVar.get()`` method,
        and you can safely use ``.get_raw()`` when you need performance.

        See also, documentation for this method in the standard library:
        :meth:`contextvars.ContextVar.get`.
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def is_set(self) -> bool:
        """Ceck if the variable has a value.

        Examples::

            >>> timezone_var = ContextVarDescriptor('timezone_var')
            >>> timezone_var.is_set()
            False

            >>> timezone_var = ContextVarDescriptor('timezone_var', default='UTC')
            >>> timezone_var.is_set()
            False

            >>> timezone_var.set('GMT')
            <Token ...>
            >>> timezone_var.is_set()
            True

            >>> timezone_var.reset_to_default()
            >>> timezone_var.is_set()
            False

            >>> timezone_var.set(None)
            <Token ...>
            >>> timezone_var.is_set()
            True

            >>> timezone_var.delete()
            >>> timezone_var.is_set()
            False
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def set(self, value) -> Token:
        """Call to set a new value for the context variable in the current context.

        The required *value* argument is the new value for the context variable.

        Returns a :class:`~contextvars.contextvars.Token` object that can be used to restore
        the variable to its previous value via the :meth:`~ContextVarDescriptor.reset` method.

        .. Note::

          This method is a shortcut to method of the standard ``ContextVar`` class,
          please check out its documentation: :meth:`contextvars.ContextVar.set`.
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def set_if_not_set(self, value) -> Any:
        """Set value if not yet set.

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
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def reset(self, token: Token):
        """Reset the context variable to a previous value.

        Reset the context variable to the value it had before the
        :meth:`ContextVarDescriptor.set` that created the *token* was used.

        For example::

            >>> var = ContextVar('var')

            >>> token = var.set('new value')
            >>> var.get()
            'new value'

            # After the reset call the var has no value again,
            # so var.get() would raise a LookupError.
            >>> var.reset(token)
            >>> var.get()
            Traceback (most recent call last):
            ...
            LookupError: ...

        .. Note::

          This method is a shortcut to method of the standard ``ContextVar`` class,
          please check out its documentation: :meth:`contextvars.ContextVar.reset`.
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def reset_to_default(self):
        """Reset context variable to the default value.

        Example::

            >>> timezone_var = ContextVarDescriptor('timezone_var', default='UTC')

            >>> timezone_var.set('Antarctica/Troll')
            <Token ...>

            >>> timezone_var.reset_to_default()

            >>> timezone_var.get()
            'UTC'

            >>> timezone_var.get(default='GMT')
            'GMT'

        When there is no default value, the value is erased, so ``get()`` raises ``LookupError``::

            >>> timezone_var = ContextVarDescriptor('timezone_var')

            >>> timezone_var.set('Antarctica/Troll')
            <Token ...>

            >>> timezone_var.reset_to_default()

            # ContextVar has no default value, so .get() call raises LookupError.
            >>> try:
            ...     timezone_var.get()
            ... except LookupError:
            ...     print('LookupError was raised')
            LookupError was raised

            # The exception can be avoided by passing a `default=...` value.
            timezone_var.get(default='UTC')
            'UTC'

        Also note that this method doesn't work when you re-use an existing
        :class:`contextvars.ContextVar` instance, like this::

            >>> timezone_var = ContextVar('timezone_var', default='UTC')
            >>> timezone_descriptor = ContextVarDescriptor(context_var=timezone_var)

            # The descriptor doesn't know a default value of the ContextVar() object,
            # so .reset_to_default() just erases the value.
            >>> timezone_descriptor.reset_to_default()

            >>> try:
            ...     timezone_descriptor.get()
            ... except LookupError:
            ...     print('LookupError was raised')
            LookupError was raised
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def delete(self):
        """Delete value stored in the context variable.

        Example::

            # Create a context variable, and set a value.
            >>> timezone_var = ContextVarDescriptor('timezone_var')
            >>> timezone_var.set('Europe/London')
            <Token ...>

            # ...so .get() call doesn't raise an exception and returns the value that was set
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

        Also note that a ``.delete()`` call doesn't reset value to default::

            >>> timezone_var = ContextVarDescriptor('timezone_var', default='UTC')

            # Before .delete() is called, .get() returns the `default=UTC` that was passed above
            >>> timezone_var.get()
            'UTC'

            # Call .delete(). That erases the default value.
            >>> timezone_var.delete()

            # Now .get() will throw LookupError, as if there was no default value at the beginning.
            >>> try:
            ...     timezone_var.get()
            ... except LookupError:
            ...     print('LookupError was raised')
            LookupError was raised

            # ...but you still can provide default as argument to ``.get()``
            >>> timezone_var.get(default='UTC')
            'UTC'

        .. Note::

            Python doesn't provide any built-in way to erase a context variable.
            So, deletion is implemented in a bit hacky way...

            When you call :meth:`~delete`, a special marker object called ``ContextVarValueDeleted``
            is written into the context variable. The :meth:`~get` method detects that marker,
            and behaves as if there was no value.

            That happens under the hood, and normally you shouldn't notice that, unless you use
            lower-level methods like :meth:`get_raw` or :meth:`contextvars.ContextVar.get`::

                >>> timezone_var.get_raw()
                contextvars_extras.descriptor.ContextVarValueDeleted

                >>> timezone_var.context_var.get()
                contextvars_extras.descriptor.ContextVarValueDeleted
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_fast_methods``.
        # It exists only for auto-generated documentation and static code analysis tools.
        raise AssertionError

    def __get__(self, instance, _unused_owner_cls):
        if instance is None:
            return self
        try:
            return self.get()
        except LookupError as err:
            raise ContextVarNotSetError.format(context_var_name=self.name) from err

    def __set__(self, instance, value):
        assert instance is not None
        self.set(value)

    def __delete__(self, instance):
        self.__get__(instance, None)  # needed to raise AttributeError if already deleted
        self.delete()

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"


class ContextVarNotSetError(ExceptionDocstringMixin, AttributeError, LookupError):
    """Context variable is not set: '{context_var_name}'.

    This exception is usually raised when you declare a context variable without a default value,
    like this:

        >>> from contextvars_extras.registry import ContextVarsRegistry
        >>> class Current(ContextVarsRegistry):
        ...     timezone: str
        >>> current = Current()

    In this case, the variable remains unitialized (as if the attribute was never set),
    so an attempt to read the attribute will raise an exception::

        >>> current.timezone
        Traceback (most recent call last):
        ...
        contextvars_extras.descriptor.ContextVarNotSetError: ...

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
