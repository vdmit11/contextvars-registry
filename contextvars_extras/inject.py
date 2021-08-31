import contextvars
import dataclasses
import functools
import inspect
import re
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Iterable,
    NewType,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

from contextvars_extras.descriptor import ContextVarDescriptor
from contextvars_extras.registry import ContextVarsRegistry
from contextvars_extras.util import Decorator, ReturnedValue, WrappedFn

# shortcuts, needed just to make code slightly more readable
_EMPTY = inspect.Parameter.empty
_KEYWORD_ONLY = inspect.Parameter.KEYWORD_ONLY
_POSITIONAL_OR_KEYWORD = inspect.Parameter.POSITIONAL_OR_KEYWORD


def inject_vars(*configs, **per_arg_configs) -> Decorator:
    """Inject context variables as arguments to a function.

    Example of use with ``ContextVarsRegistry``::

        >>> from contextvars_extras.registry import ContextVarsRegistry
        >>> class Current(ContextVarsRegistry):
        ...     timezone: str = 'UTC'
        ...     locale: str = 'en'
        >>> current = Current()

        >>> @inject_vars(current)
        ... def print_vars(locale, timezone):
        ...     print(f"locale: {locale}")
        ...     print(f"timezone: {timezone}")

        >>> print_vars()
        locale: en
        timezone: UTC

        >>> print_vars(timezone='Antarctica/Troll')
        locale: en
        timezone: Antarctica/Troll

        >>> with current(locale='nb', timezone='Antarctica/Troll'):
        ...     print_vars()
        locale: nb
        timezone: Antarctica/Troll

    Use with classic ``ContextVar`` objects (without registry)::

        >>> from contextvars import ContextVar
        >>> timezone_var = ContextVar('my_project.timezone', default='UTC')
        >>> locale_var = ContextVar('my_project.locale', default='en')

        >>> @inject_vars(timezone_var, locale_var)
        ... def print_vars(*, locale, timezone):
        ...     print(f"locale: {locale}")
        ...     print(f"timezone: {timezone}")

        >>> print_vars()
        locale: en
        timezone: UTC

    Explicitly route variables to parameters::

        >>> @inject_vars(
        ...    timezone=timezone_var,  # use ContextVar object
        ...    locale=Current.locale,  # use ContextVarDescriptor (member of ContextVarsRegistry)
        ...    user_id=current,  # use current.user_id attribute
        ... )
        ... def print_vars(user_id=None, timezone=None, locale=None):
        ...     print(f"user_id: {user_id}")
        ...     print(f"locale: {locale}")
        ...     print(f"timezone: {timezone}")

        >>> print_vars()
        user_id: None
        locale: en
        timezone: UTC
    """

    def _decorator__inject_vars(wrapped_fn: WrappedFn) -> WrappedFn:
        rules = _generate_injection_rules(wrapped_fn, configs, per_arg_configs)
        rules_list = list(rules)

        @functools.wraps(wrapped_fn)
        def _wrapper__inject_vars(*args, **kwargs) -> ReturnedValue:
            _execute_injection_rules(rules_list, args, kwargs)
            return wrapped_fn(*args, **kwargs)

        return _wrapper__inject_vars

    return _decorator__inject_vars


@dataclasses.dataclass(frozen=True)
class InjectionConfig:
    """Structure for arguments of the ``@inject_vars`` decorator.

    Arguments to the :func:`inject_vars` decorator can come in several different forms.

    It is a bit of hassle to take into accoutn all these different forms of arguments everywhere,
    so they're all normalized, and converted to ``InjectionConfig`` objects.

    So that, for example, this::

        @inject_vars(registry)

    internally is converted to::

        [
            InjectionConfig(source=registry)
        ]


    Keyword arguments are also converted to ``InjectionConfig`` objects::

        @inject_vars(
            locale=registry,
            timezone=registry,
            user_id=user_id_context_var,
        )
        # internally converted to:
        [
            InjectionConfig(names=['locale'], source=registry),
            InjectionConfig(names=['timezone'], source=registry),
            InjectionConfig(names=['user_id'], source=user_id_context_var),
        ]


    ...and dictionaries are also converted to ``InjectionConfig`` objects::

         @inject_vars(
             {
                 'names': ['locale', 'timezone'],
                 'source': registry,
             },
             {
                 'names': ['user_id']
                 'source': user_id_context_var,
             }
         )
         # internally converted to:
         [
             InjectionConfig(names=['locale', 'timezone'], source=registry),
             InjectionConfig(names=['user_id'], source=user_id_context_var),
         ]

    Each argument to ``@inject_vars()`` becomes a ``InjectionConfig`` instance.
    This process is called here "normalization".

    So after the normalization procedure, all different forms of arguments become just a stream
    of ``InjectionConfig`` objects, with well-known structure, which is easy to deal with
    (much easier than coding if/else branches to support several forms of arguments everywhere).

    .. NOTE::

      This class is for internal use only.
      It shouldn't be used outside of this module.

      However, you can still use it as documentation to get an idea of
      which keys you can use when you pass dictionary configs to the decorator.
    """

    source: Any
    """Source of values injected as arguments to functions.

    It can be:

      - a ``contextvars.ContextVar`` object
        (then its ``.get()`` method is called to obtain the injected value)

      - :class:`~contextvars_extras.descriptor.ContextVarDescriptor`
        (same as ``ContextVar``: the ``.get()`` method is called)

      - :class:`~contextvars_extras.registry.ContextVarsRegistry`
        (then context variables stored in the registry are injected as function arguments)

      - arbitrary object, e.g.: ``@inject_vars(flask.g)``
        (then object attributes are injected as arguments to the called functions)

      - arbitrary function, e.g.: ``@inject_vars(locale=get_current_locale)``
        (then the function is just called to obtain the injected value)

    This list of behaviors can be extended via the :func:`choose_inject_getter_fn` function.
    """

    names: Optional[Collection[str]] = None
    """Names of injected parameters.

    A source may match to many parameters simultaneously, for example::

        @inject_vars({
            'source': registry,
            'names': ['locale', 'timezone']
        })
        def fn(user_id=None, timezone=None, locale=None):
            pass

    In that example, the ``registry`` object is used to inject both ``locale`` and ``timezone``
    (whereas ``user_id`` is not injected at all).

    This ``names`` member is optional.
    If not provided, the ``names`` are chosen automatically, depending on the ``source``:

      - for ``ContextVar`` objects, the parameter name is guessed from ``ContextVar.name`` attribute
      - for ``ContextVarRegistry``, and all other types of sources, the ``names`` list by
        default is filled with all function parameters (so ALL arguments become injected).

    This name guessing behavior can be extended via the :func:`choose_inject_names` function.
    """


ParamsDict = NewType(
    "ParamsDict",
    Dict[
        str,  # parameter name
        Tuple[
            Optional[int],  # position
            Any,  # default value
        ],
    ],
)


def _get_params_available_for_injection(fn: Callable) -> ParamsDict:
    sig = inspect.signature(fn)

    out = {}
    position: Optional[int]

    for position, param in enumerate(sig.parameters.values()):
        # I can't imagine a situation, where you really need to inject a positional parameter,
        # or you need to inject those variable *args/**kwargs parameters. So ignore them.
        if param.kind not in (_KEYWORD_ONLY, _POSITIONAL_OR_KEYWORD):
            continue

        if param.kind is _KEYWORD_ONLY:
            position = None

        out[param.name] = (position, param.default)

    return ParamsDict(out)


# GetterFn - type definition for getter functions.
#
# We call "getter" a function of 1 parameter, that (roughly) looks like this:
#
#     def getter(default):
#         return some_value or default
#
# A getter function should somehow get a value, or return the ``default`` argument
# (a special marker object) to indicate that value is not available.
Default = TypeVar("Default")
GetterFn = Callable[[Default], Union[Any, Default]]


# InjectionRuleTuple - a prepared "instruction" for the ``@inject_vars`` decorator.
#
# Problem: there is some magic in how arguments of the :func:`inject_context_args` decorator
# are processed, and this magic is a bit slow.
#
# Well, maybe not really slow, but there is some overhead, which is summed up and becomes
# noticeable when you decorate a lot of functions.
#
# As a solution, we have a little premature optimization: the :func:`inject_vars`
# decorator pre-processes its arguments, and sort of compiles them into rules.
#
# One such ``InjectionRuleTuple`` is a primitive instruction that (roughly) says:
#   - "call this getter function, and put the returned value to function arguments"
#
# And later on, when the decorated function is actually called, the prepared rules are executed.
#
# So the overhead of the ``@inject_vars`` decorator is reduced down to just executing
# primitive rules (basically calling a bunch of prepared getter functions in sequence).
InjectionRuleTuple = NewType(
    "InjectionRuleTuple",
    Tuple[
        # parameter name
        str,
        # parameter position (None for KEYWORD_ONLY parameters)
        Optional[int],
        # parameter default value
        Any,
        # getter function that fetches value from some context variable
        GetterFn,
    ],
)


def _execute_injection_rules(rules: Sequence[InjectionRuleTuple], args: tuple, kwargs: dict):
    args_count = len(args)

    for (name, position, default, getter) in rules:
        # Argument is passed? No need to inject anything then.
        if name in kwargs:
            continue

        if (position is not None) and (position < args_count):
            continue

        # call the getter function that somehow fetches the value from the global variable
        value = getter(default)
        if value is _EMPTY:
            continue

        # inject the value into kwargs
        kwargs[name] = value


def _generate_injection_rules(
    wrapped_fn: Callable,
    configs: tuple,
    per_arg_configs: dict,
) -> Iterable[InjectionRuleTuple]:
    params = _get_params_available_for_injection(wrapped_fn)

    for name, value in per_arg_configs.items():
        config = _normalize_inject_decorator_arg(name, value)
        yield from _generate_rules_for_single_config(config, params)

    for value in configs:
        config = _normalize_inject_decorator_arg(None, value)
        yield from _generate_rules_for_single_config(config, params)


def _generate_rules_for_single_config(
    config: InjectionConfig, params: ParamsDict
) -> Iterable[InjectionRuleTuple]:
    names = config.names or choose_inject_names(config.source, available_names=params.keys())
    for name in names:
        position, default = params[name]
        getter_fn = choose_inject_getter_fn(config.source, name=name)
        rule: InjectionRuleTuple = InjectionRuleTuple((name, position, default, getter_fn))
        yield rule


def _normalize_inject_decorator_arg(name, value) -> InjectionConfig:
    if isinstance(value, dict):
        if name:
            config = InjectionConfig(**value, names=[name])
        else:
            config = InjectionConfig(**value)
    else:
        if name:
            config = InjectionConfig(source=value, names=[name])
        else:
            config = InjectionConfig(source=value)

    return config


@functools.singledispatch
def choose_inject_names(source: Any, available_names: Collection[str], **kwargs) -> Collection[str]:
    return available_names


_identifier_regex = re.compile(r"[^\d\W]\w*\Z")


@choose_inject_names.register(contextvars.ContextVar)
@choose_inject_names.register(ContextVarDescriptor)
def _injected_names_for_context_var(ctx_var, available_names, **kwargs):
    found_names = _identifier_regex.findall(ctx_var.name)
    assert len(found_names) == 1
    return found_names


@functools.singledispatch
def choose_inject_getter_fn(source: object, name: str, **kwargs) -> GetterFn:
    if callable(source):
        return source

    return functools.partial(getattr, source, name)


@choose_inject_getter_fn.register(contextvars.ContextVar)
@choose_inject_getter_fn.register(ContextVarDescriptor)
def _getter_for_context_var(ctx_var: contextvars.ContextVar, **kwargs) -> GetterFn:
    def _get_ctxvar_value_or_default(default):
        try:
            return ctx_var.get()
        except LookupError:
            return default

    return _get_ctxvar_value_or_default


@choose_inject_getter_fn.register
def _getter_for_registry(registry: ContextVarsRegistry, name: str, **kwargs) -> GetterFn:
    return functools.partial(getattr, registry, name)
