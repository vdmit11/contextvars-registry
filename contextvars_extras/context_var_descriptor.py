"""ContextVarDescriptor - extension for the built-in ContextVar that behaves like @property."""

from contextvars import ContextVar
from typing import Any, Callable, Generic, Optional, Type, TypeVar, Union, overload

from contextvars_extras.context_var_ext import ContextVarExt, VarValueT
from contextvars_extras.internal_utils import ExceptionDocstringMixin
from contextvars_extras.sentinel import MISSING, Missing

_DescriptorT = TypeVar("_DescriptorT")  # ContextVarDescriptor or its subclass
_OwnerT = TypeVar("_OwnerT")  # descriptor's owner (an object that contains descriptor as attribute)


class ContextVarDescriptor(Generic[VarValueT], ContextVarExt[VarValueT]):
    def __init__(
        self,
        name: Optional[str] = None,
        default: Union[VarValueT, Missing] = MISSING,
        deferred_default: Optional[Callable[[], VarValueT]] = None,
        context_var: Optional[ContextVar[VarValueT]] = None,
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

        :param context_var: A reference to an existing ``ContextVar`` object.
                            You need it only if you want to re-use an existing object.
                            If missing, a new ``ContextVar`` object is created automatically.
        """
        if not name and not context_var:
            # postpone init until __set_name__() method is called
            self._postponed_init_args = (default, deferred_default)
            return

        super().__init__(
            name=name,
            default=default,
            deferred_default=deferred_default,
            context_var=context_var,
        )

    def __set_name__(self, owner_cls: type, owner_attr_name: str) -> None:
        if hasattr(self, "_postponed_init_args"):
            default, deferred_default = self._postponed_init_args
            name = self._format_descriptor_name(owner_cls, owner_attr_name)
            self._init_with_creating_new_context_var(  # type: ignore
                name, default, deferred_default
            )

    @staticmethod
    def _format_descriptor_name(owner_cls: type, owner_attr_name: str) -> str:
        return f"{owner_cls.__module__}.{owner_cls.__name__}.{owner_attr_name}"

    @overload
    def __get__(self: _DescriptorT, owner_instance: None, owner_cls: Type[_OwnerT]) -> _DescriptorT:
        ...

    @overload
    def __get__(self, owner_instance: _OwnerT, owner_cls: Type[_OwnerT]) -> VarValueT:
        ...

    @overload
    def __get__(
        self: _DescriptorT, owner_instance: Any, owner_cls: Any
    ) -> Union[_DescriptorT, VarValueT]:
        ...

    def __get__(self, owner_instance, owner_cls):
        if owner_instance is None:
            return self
        try:
            return self.get()
        except LookupError as err:
            raise ContextVarNotSetError.format(context_var_name=self.name) from err

    def __set__(self, owner_instance, value: VarValueT) -> None:
        assert owner_instance is not None
        self.set(value)

    def __delete__(self, owner_instance) -> None:
        self.__get__(owner_instance, None)  # needed to raise AttributeError if already deleted
        self.delete()


class ContextVarNotSetError(ExceptionDocstringMixin, AttributeError, LookupError):
    """Context variable is not set: '{context_var_name}'.

    This exception is usually raised when you declare a context variable without a default value,
    like this:

        >>> from contextvars_extras import ContextVarsRegistry
        >>> class Current(ContextVarsRegistry):
        ...     timezone: str
        >>> current = Current()

    In this case, the variable remains unitialized (as if the attribute was never set),
    so an attempt to read the attribute will raise an exception::

        >>> current.timezone
        Traceback (most recent call last):
        ...
        contextvars_extras.context_var_descriptor.ContextVarNotSetError: ...

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
