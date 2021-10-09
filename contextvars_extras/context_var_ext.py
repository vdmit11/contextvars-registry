"""ContextVarExt - extension for the built-in ContextVar object."""

from contextvars import ContextVar, Token
from typing import Any, Callable, Optional

from contextvars_extras.util import Missing, Sentinel

# A special sentinel object that we put into ContextVar when you delete a value from it
# (when ContextVarExt.delete() method is called).
ContextVarValueDeleted = Sentinel(__name__, "ContextVarValueDeleted")

# Another special marker that we put into ContextVar when it is not yet initialized,
# used in 2 cases:
#  1. when ContextVarExt(deferred_default=...) argument is used
#  2. when ContextVarExt.reset_to_default() method is called
ContextVarNotInitialized = Sentinel(__name__, "ContextVarNotInitialized")

# A no-argument function that produces a default value for ContextVarExt
DeferredDefaultFn = Callable[[], Any]


class ContextVarExt:
    context_var: ContextVar
    name: str
    _default: Any
    _deferred_default: Optional[DeferredDefaultFn]

    def __init__(
        self,
        name: Optional[str] = None,
        default: Optional[Any] = Missing,
        deferred_default: Optional[DeferredDefaultFn] = None,
        context_var: Optional[ContextVar] = None,
    ):
        """Initialize ContextVarExt object.

        :param name: Name for the underlying ``ContextVar`` object.
                     Needed for introspection and debugging purposes.

        :param default: The default value for the  underlying ``ContextVar`` object.
                        Returned by the ``get()`` method if the variable is not bound to a value.
                        If default is missing, then ``get()`` may raise ``LookupError``.

        :param deferred_default: A function that produces a default value.
                                 Called by ``get()`` method, once per context.
                                 That is, if you spawn 10 threads, then ``deferred_default()``
                                 is called 10 times, and you get 10 thread-local values.

        :param context_var: A reference to an existing ``ContextVar`` object.
                            You need it only if you want to re-use an existing object.
                            If missing, a new ``ContextVar`` object is created automatically.
        """
        assert name or context_var
        assert not ((default is not Missing) and (deferred_default is not None))
        self._default = default
        self._deferred_default = deferred_default

        if context_var:
            assert not name and not default
            self._init_context_var(context_var)
        else:
            assert name
            context_var = self._new_context_var(name, default)
            self._init_context_var(context_var)

    @classmethod
    def _new_context_var(cls, name: str, default: Any) -> ContextVar:
        context_var: ContextVar

        if default is Missing:
            context_var = ContextVar(name)
        else:
            context_var = ContextVar(name, default=default)

        return context_var

    def _init_context_var(self, context_var: ContextVar):
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
        # the ContextVarExt() instance.
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
        context_var_ext_default = self._default
        context_var_ext_deferred_default = self._deferred_default

        # Local variables are faster than globals.
        # So, copy all needed globals and thus make them locals.
        _Missing = Missing
        _ContextVarValueDeleted = ContextVarValueDeleted
        _ContextVarNotInitialized = ContextVarNotInitialized
        _LookupError = LookupError

        # Ok, now define closures that use all the variables prepared above.

        # NOTE: function name is chosen such that it looks good in stack traces.
        # When an exception is thrown, just "get" looks cryptic, while "_method_ContextVarExt_get"
        # at least gives you a hint that the ContextVarExt.get method is the source of exception.
        def _method_ContextVarExt_get(default=_Missing):
            if default is _Missing:
                value = context_var_get()
            else:
                value = context_var_get(default)

            # special marker, left by ContextVarExt.reset_to_default()
            if value is _ContextVarNotInitialized:
                if default is not _Missing:
                    return default
                if context_var_ext_default is not _Missing:
                    return context_var_ext_default
                if context_var_ext_deferred_default is not None:
                    value = context_var_ext_deferred_default()
                    context_var_set(value)
                    return value
                raise _LookupError(context_var)

            # special marker, left by ContextVarExt.delete()
            if value is _ContextVarValueDeleted:
                if default is not _Missing:
                    return default
                raise _LookupError(context_var)

            return value

        self.get = _method_ContextVarExt_get

        def _method_ContextVarExt_is_set() -> bool:
            return context_var_get(_Missing) not in (
                _Missing,
                _ContextVarValueDeleted,
                _ContextVarNotInitialized,
            )

        self.is_set = _method_ContextVarExt_is_set

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

            >>> locale_var = ContextVarExt('locale_var', default='UTC')

            >>> locale_var.get()
            'UTC'

            >>> locale_var.set('Europe/London')
            <Token ...>

            >>> locale_var.get()
            'Europe/London'


        Note that if that if there is no ``default`` value, it may raise ``LookupError``::

            >>> locale_var = ContextVarExt('locale_var')

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

            >>> timezone_var = ContextVarExt('timezone_var')

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

            >>> timezone_var = ContextVarExt('timezone_var')
            >>> timezone_var.is_set()
            False

            >>> timezone_var = ContextVarExt('timezone_var', default='UTC')
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
        the variable to its previous value via the :meth:`~ContextVarExt.reset` method.

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

            >>> locale_var = ContextVarExt('locale_var', default='en')

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
        existing_value = self.get(_NotSet)

        if existing_value is _NotSet:
            self.set(value)
            return value

        return existing_value

    def reset(self, token: Token):
        """Reset the context variable to a previous value.

        Reset the context variable to the value it had before the
        :meth:`ContextVarExt.set` that created the *token* was used.

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

            >>> timezone_var = ContextVarExt('timezone_var', default='UTC')

            >>> timezone_var.set('Antarctica/Troll')
            <Token ...>

            >>> timezone_var.reset_to_default()

            >>> timezone_var.get()
            'UTC'

            >>> timezone_var.get(default='GMT')
            'GMT'

        When there is no default value, the value is erased, so ``get()`` raises ``LookupError``::

            >>> timezone_var = ContextVarExt('timezone_var')

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
            >>> timezone_var_ext = ContextVarExt(context_var=timezone_var)

            # ContextVarExt() wrapper doesn't know a default value of the underlying ContextVar()
            # object, so .reset_to_default() just erases the value.
            >>> timezone_var_ext.reset_to_default()

            >>> try:
            ...     timezone_var_ext.get()
            ... except LookupError:
            ...     print('LookupError was raised')
            LookupError was raised
        """
        self.set(ContextVarNotInitialized)

    def delete(self):
        """Delete value stored in the context variable.

        Example::

            # Create a context variable, and set a value.
            >>> timezone_var = ContextVarExt('timezone_var')
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
        """
        self.set(ContextVarValueDeleted)

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"


# A special sentinel object, used only by the ContextVarExt.set_if_not_set() method.
_NotSet = Sentinel(__name__, "_NotSet")
