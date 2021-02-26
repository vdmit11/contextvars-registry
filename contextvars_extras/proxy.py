from abc import ABC
from contextvars import ContextVar, Token
from typing import get_type_hints

from contextvars_extras.util import dedent_strip


MISSING = Token.MISSING


class ContextVarsProxy(ABC):
    """A collection of ContextVar() objects, with nice @property-like way to access them.

    The idea is simple: you create a sub-class, and declare your variables using type annotations:

        >>> class CurrentVars(ContextVarsProxy):
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
        <ContextVarDescriptor name='contextvars_extras.proxy.CurrentVars.timezone'...>

    and its underlying ContextVar can be reached via the `.context_var` attribute:

        >>> CurrentVars.timezone.context_var
        <ContextVar name='contextvars_extras.proxy.CurrentVars.timezone'...>

    But in practice, you normally shouldn't need that.
    ContextVarDescriptor should implement all same attributes and methods as ContextVar,
    and thus it can be used instead of ContextVar() object in all cases except isinstance() checks.
    """

    @classmethod
    def __init_subclass__(cls):
        cls._init_class_attrs_as_contextvars()

    @classmethod
    def _init_class_attrs_as_contextvars(cls):
        hinted_attrs = get_type_hints(cls)
        for attr_name in hinted_attrs:
            cls._init_attr_as_contextvar(attr_name)

    @classmethod
    def _init_attr_as_contextvar(cls, attr_name) -> ContextVar:
        default = getattr(cls, attr_name, MISSING)

        assert not isinstance(default, (ContextVar, ContextVarDescriptor))

        var_name = f"{cls.__module__}.{cls.__name__}.{attr_name}"
        new_var_descriptor = ContextVarDescriptor(var_name, default)

        setattr(cls, attr_name, new_var_descriptor)

    def __init__(self):
        cls = self.__class__
        if cls == ContextVarsProxy:
            raise NotImplementedError(
                dedent_strip(
                    f"""
                class {cls.__name__} cannot be instanciated directly without sub-classing.

                You have to create a sub-class before using it:

                    class CurrentVars({cls.__name__}):
                        var1: str = "default_value"

                    current = CurrentVars()
                    current.var1   # => "default_value"
                """
                )
            )


class ContextVarDescriptor:
    context_var: ContextVar

    def __init__(self, name, default=MISSING):
        if default is MISSING:
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
        return self.context_var.get()

    def __set__(self, instance, value):
        assert instance is not None
        self.context_var.set(value)

    def __repr__(self):
        if self.default is MISSING:
            return f"<{self.__class__.__name__} name={self.name}>"
        else:
            return f"<{self.__class__.__name__} name={self.name!r} default={self.default!r}>"
