from contextvars import ContextVar, Token
from typing import Any, Optional

from contextvars_extras.util import ExceptionDocstringMixin, Missing


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

    def __init__(
        self,
        name: Optional[str] = None,
        default: Optional[Any] = Missing,
        owner_cls: Optional[type] = None,
        owner_attr: Optional[str] = None,
        context_var: Optional[ContextVar] = None,
    ):
        """Initialize ContextVarDescriptor object.

        :param default: The default value for the  underlying ``ContextVar`` object.
                        Returned by the ``get()`` method if the variable is not bound to a value.
                        If default is missing, then ``get()`` may raise ``LookupError``.

        :param name: Name for the underlying ``ContextVar`` object.
                     Needed for introspection and debugging purposes.
                     Ususlly you don't want to set it manually, because it is automatically
                     formatted from owner class/attribute names.

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
        if context_var:
            assert not name and not default
            self._set_context_var(context_var)
        elif name:
            context_var = self._new_context_var(name, default)
            self._set_context_var(context_var)
        elif owner_cls and owner_attr:
            context_var = self._new_context_var_for_owner(owner_cls, owner_attr, default)
            self._set_context_var(context_var)
        else:
            self._default = default

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

        self.context_var = context_var
        self.name = context_var.name

        self._initialize_get_set_reset_methods()

    def _initialize_get_set_reset_methods(self):
        # Problem: performance is a must for basic ContextVar.get()/set()/reset() methods.
        #
        # Guess this one of the main reasons why they're implemented in C, as Python extensions.
        #
        # We don't want to impose any extra Python-level overhead on top of C functions,
        # so here is a trick: copy methods from underlying ContextVar object.
        #
        # So by calling, for example ``ContextVarRegistry.set()``, you're *actually*
        # directly calling the underlying ``ContextVar.set`` (the low-level C function).
        self.get = self.context_var.get
        self.set = self.context_var.set
        self.reset = self.context_var.reset

    def get(self, default=Missing):
        """Return a value for the context variable for the current context.

        If there is no value for the variable in the current context,
        the method will:

          * return the value of the ``default`` argument of the method, if provided; or
          * return the default value for the context variable, if it was created with one; or
          * raise a :exc:`LookupError`.

        .. Note::

          This method is a direct referrence to method of the standard ``ContextVar`` class,
          check this out::

              >>> timezone_var = ContextVarDescriptor('timezone_var')

              >>> timezone_var.get
              <built-in method get of ContextVar object ...>

              >>> timezone_var.get == timezone_var.context_var.get
              True

          please check out its documentation: :meth:`contextvars.ContextVar.get`.
        """
        # pylint: disable=no-self-use,method-hidden
        # This code is never actually called, see ``_initialize_get_set_reset_methods``.
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
        # This code is never actually called, see ``_initialize_get_set_reset_methods``.
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
        # This code is never actually called, see ``_initialize_get_set_reset_methods``.
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

    def __delete__(self, _unused_instance):
        raise DeleteIsNotImplementedError.format(context_var_name=self.name)

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
