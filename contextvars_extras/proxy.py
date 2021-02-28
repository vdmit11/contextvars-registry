import threading
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

    _var_init_on_setattr: bool = True
    """Automatically initialize missing ContextVar() objects when setting attributes?

    If set to True (default), missing ContextVar() objects are automatically created when
    setting attributes. That is, you can define an empty class, and then set arbitrary attributes:

        >>> class CurrentVars(ContextVarsProxy):
        ...    pass

        >>> current = CurrentVars()
        >>> current.locale = 'en'
        >>> current.timezone = 'UTC'

    However, if you find this behavior weak, you may disable it, like this:

        >>> class CurrentVars(ContextVarsProxy):
        ...     _var_init_on_setattr = False
        ...     locale: str = 'en'

        >>> current = CurrentVars()
        >>> current.timezone = 'UTC'
        AttributeError: ...
    """

    _var_init_lock: threading.RLock
    """A lock that protects initialization of the class attributes as context variables.

    ContextVar() objects are lazily created on 1st attempt to set an attribute.
    So a race condition is possible: multiple concurrent threads (or co-routines)
    set an attribute for the 1st time, and thus create multiple ContextVar() objects.
    The last created ContextVar() object wins, and others are lost, causing a memory leak.

    So this lock is needed to ensure that ContextVar() object is created only once.
    """

    _var_init_done_attrs: set
    """Names of attributes that were initialized as context variables.

    Can be mutated at run time, when missing ContextVar() objects are created
    dynamically (on the 1st attempt to set an attribute).
    """

    @classmethod
    def __init_subclass__(cls):
        cls._var_init_done_attrs = set()
        cls._var_init_lock = threading.RLock()
        cls._var_init_type_hinted_attrs_as_descriptors()

    @classmethod
    def _var_init_type_hinted_attrs_as_descriptors(cls):
        hinted_attrs = get_type_hints(cls)
        for attr_name in hinted_attrs:
            cls._var_init_attr_as_descriptor(attr_name)

    @classmethod
    def _var_init_attr_as_descriptor(cls, attr_name):
        with cls._var_init_lock:
            if attr_name in cls._var_init_done_attrs:
                return

            if attr_name.startswith('_var_'):
                return

            value = getattr(cls, attr_name, MISSING)
            assert not isinstance(value, (ContextVar, ContextVarDescriptor))

            var_name = f"{cls.__module__}.{cls.__name__}.{attr_name}"
            new_var_descriptor = ContextVarDescriptor(var_name, default=value)
            setattr(cls, attr_name, new_var_descriptor)

            cls._var_init_done_attrs.add(attr_name)

    def __setattr__(self, attr_name, value):
        if attr_name not in self._var_init_done_attrs:
            if not self._var_init_on_setattr:
                class_name = self.__class__.__name__
                raise AttributeError(dedent_strip(
                    f"""
                    Can't set undeclared attribute: {class_name}.{attr_name}

                    Maybe there is a typo in the attribute name?

                    If this is a new attribute, then you have to first declare it in the class,
                    with a type hint, like this:

                    class {class_name}(...):
                        {attr_name}: {type(value).__name__} = default_value
                    """
                ))

            if attr_name.startswith('_var_'):
                raise AttributeError(dedent_strip(
                    f"""
                    Can't set attribute '{attr_name}' because of special '_var_' prefix.

                    '_var_' prefix is reserved for ContextVarProxy class settings.
                    You can't set such attribute on the instance level.

                    If you want to configure the class, you should do it on the class level:
                    like this:

                        class {self.__class__.__name__}(...):
                            {attr_name}: {type(value).__name__} = {value!r}
                    """
                ))

            self._var_init_attr_as_descriptor(attr_name)

        super().__setattr__(attr_name, value)

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
