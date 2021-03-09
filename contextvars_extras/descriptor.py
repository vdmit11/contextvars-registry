from contextvars import ContextVar

from contextvars_extras.util import ExceptionDocstringMixin, Missing


class ContextVarDescriptor:
    context_var: ContextVar

    def __init__(self, name, default=Missing):
        if default is Missing:
            self.context_var = ContextVar(name)
        else:
            self.context_var = ContextVar(name, default=default)

        self.name = self.context_var.name
        self.get = self.context_var.get
        self.set = self.context_var.set
        self.reset = self.context_var.reset

        self.default = default

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

    def __delete__(self, _unused_instance):
        raise DeleteIsNotImplementedError.format(context_var_name=self.name)

    def __repr__(self):
        if self.default is Missing:
            out = f"<{self.__class__.__name__} name={self.name}>"
        else:
            out = f"<{self.__class__.__name__} name={self.name!r} default={self.default!r}>"
        return out


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


class DeleteIsNotImplementedError(ExceptionDocstringMixin, NotImplementedError):
    """Can't delete context variable: '{context_var_name}'.

    This exception is raised when you try to delete an attribute of :class:`ContextVarsRegistry`
    like this::

        >>> from contextvars_extras.registry import ContextVarsRegistry
        >>> class Current(ContextVarsRegistry):
        ...     user_id: int
        >>> current = Current()

        >>> current.user_id = 42
        >>> del current.user_id
        Traceback (most recent call last):
        ...
        contextvars_extras.descriptor.DeleteIsNotImplementedError: ...

    This is caused by the fact, that ``contextvars.ContextVar`` object cannot be garbage-collected,
    so deleting it causes a memory leak. In addition, the standard library doesn't provide any API
    for erasing values stored inside ``ContextVar`` objects.

    So context variables cannot be deleted or erased.
    This is a technical limitation. Deal with it.

    A possible workaround is to use a ``with`` block to set context variables temporarily:

        >>> with current(user_id=100):
        ...    print(current.user_id)
        100
    """
