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


def args_from_context(*sources, **per_arg_sources) -> Decorator:
    """Take arguments from context variables.

    Example of use with ``ContextVarsRegistry``::

        >>> from contextvars_extras.registry import ContextVarsRegistry
        >>> class Current(ContextVarsRegistry):
        ...     timezone: str = 'UTC'
        ...     locale: str = 'en'
        >>> current = Current()

        >>> @args_from_context(current)
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

        >>> @args_from_context(timezone_var, locale_var)
        ... def print_vars(*, locale, timezone):
        ...     print(f"locale: {locale}")
        ...     print(f"timezone: {timezone}")

        >>> print_vars()
        locale: en
        timezone: UTC

    Explicitly route variables to parameters::

        >>> @args_from_context(
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

    def _decorator__args_from_context(wrapped_fn: WrappedFn) -> WrappedFn:
        rules = _generate_injection_rules(wrapped_fn, sources, per_arg_sources)
        rules_list = list(rules)

        @functools.wraps(wrapped_fn)
        def _wrapper__args_from_context(*args, **kwargs) -> ReturnedValue:
            _execute_injection_rules(rules_list, args, kwargs)
            return wrapped_fn(*args, **kwargs)

        return _wrapper__args_from_context

    return _decorator__args_from_context


@dataclasses.dataclass(frozen=True)
class ArgSourceSpec:
    """Structure for arguments of the ``@args_from_context`` decorator.

    Arguments to the :func:`args_from_context` decorator can come in several different forms.

    It is a bit of hassle to take into accoutn all these different forms of arguments everywhere,
    so they're all normalized, and converted to ``ArgSourceSpec`` objects.

    So that, for example, this::

        @args_from_context(registry)

    internally is converted to::

        [
            ArgSourceSpec(source=registry)
        ]


    Keyword arguments are also converted to ``ArgSourceSpec`` objects::

        @args_from_context(
            locale=registry,
            timezone=registry,
            user_id=user_id_context_var,
        )
        # internally converted to:
        [
            ArgSourceSpec(names=['locale'], source=registry),
            ArgSourceSpec(names=['timezone'], source=registry),
            ArgSourceSpec(names=['user_id'], source=user_id_context_var),
        ]


    ...and dictionaries are also converted to ``ArgSourceSpec`` objects::

         @args_from_context(
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
             ArgSourceSpec(names=['locale', 'timezone'], source=registry),
             ArgSourceSpec(names=['user_id'], source=user_id_context_var),
         ]

    Each argument to ``@args_from_context()`` becomes a ``ArgSourceSpec`` instance.
    This process is called here "normalization".

    So after the normalization procedure, all different forms of arguments become just a stream
    of ``ArgSourceSpec`` objects, with well-known structure, which is easy to deal with
    (much easier than coding if/else branches to support several forms of arguments everywhere).

    .. NOTE::

      This class is for internal use only.
      It shouldn't be used outside of this module.

      However, you can still use it as documentation to get an idea of
      which keys you can use when you pass dictionary sources to the decorator.
    """

    source: Any
    """Source of values injected as arguments to functions.

    It can be:

      - a ``contextvars.ContextVar`` object
        (then its ``.get()`` method is called to obtain the value)

      - :class:`~contextvars_extras.descriptor.ContextVarDescriptor`
        (same as ``ContextVar``: the ``.get()`` method is called)

      - :class:`~contextvars_extras.registry.ContextVarsRegistry`
        (then context variables stored in the registry are injected as function arguments)

      - arbitrary object, e.g.: ``@args_from_context(flask.g)``
        (then object attributes are injected as arguments to the called functions)

      - arbitrary function, e.g.: ``@args_from_context(locale=get_current_locale)``
        (then the function is just called to obtain the value)

    This list of behaviors can be extended via the :func:`choose_arg_getter_fn` function.
    """

    names: Optional[Collection[str]] = None
    """Names of injected parameters.

    A source may match to many parameters simultaneously, for example::

        @args_from_context({
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

    This name guessing behavior can be extended via the :func:`choose_arg_names` function.
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


# InjectionRuleTuple - a prepared "instruction" for the ``@args_from_context`` decorator.
#
# Problem: there is some magic in how arguments of the :func:`inject_context_args` decorator
# are processed, and this magic is a bit slow.
#
# Well, maybe not really slow, but there is some overhead, which is summed up and becomes
# noticeable when you decorate a lot of functions.
#
# As a solution, we have a little premature optimization: the :func:`args_from_context`
# decorator pre-processes its arguments, and sort of compiles them into rules.
#
# One such ``InjectionRuleTuple`` is a primitive instruction that (roughly) says:
#   - "call this getter function, and put the returned value to function arguments"
#
# And later on, when the decorated function is actually called, the prepared rules are executed.
#
# So the overhead of the ``@args_from_context`` decorator is reduced down to just executing
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
    sources: tuple,
    per_arg_sources: dict,
) -> Iterable[InjectionRuleTuple]:
    params = _get_params_available_for_injection(wrapped_fn)

    for name, source in per_arg_sources.items():
        source_spec = _normalize_source_spec(name, source)
        yield from _generate_rules_for_single_source(source_spec, params)

    for source in sources:
        source_spec = _normalize_source_spec(None, source)
        yield from _generate_rules_for_single_source(source_spec, params)


def _generate_rules_for_single_source(
    source_spec: ArgSourceSpec, params: ParamsDict
) -> Iterable[InjectionRuleTuple]:
    names = source_spec.names or choose_arg_names(source_spec.source, available_names=params.keys())
    for name in names:
        position, default = params[name]
        getter_fn = choose_arg_getter_fn(source_spec.source, name=name)
        rule: InjectionRuleTuple = InjectionRuleTuple((name, position, default, getter_fn))
        yield rule


def _normalize_source_spec(name, source) -> ArgSourceSpec:
    if isinstance(source, dict):
        if name:
            source_spec = ArgSourceSpec(**source, names=[name])
        else:
            source_spec = ArgSourceSpec(**source)
    else:
        if name:
            source_spec = ArgSourceSpec(source=source, names=[name])
        else:
            source_spec = ArgSourceSpec(source=source)

    return source_spec


@functools.singledispatch
def choose_arg_names(source: Any, available_names: Collection[str], **kwargs) -> Collection[str]:
    return available_names


_identifier_regex = re.compile(r"[^\d\W]\w*\Z")


@choose_arg_names.register(contextvars.ContextVar)
@choose_arg_names.register(ContextVarDescriptor)
def _arg_names_for_context_var(ctx_var, available_names, **kwargs):
    found_names = _identifier_regex.findall(ctx_var.name)
    assert len(found_names) == 1
    return found_names


@functools.singledispatch
def choose_arg_getter_fn(source: object, name: str, **kwargs) -> GetterFn:
    if callable(source):
        return source

    return functools.partial(getattr, source, name)


@choose_arg_getter_fn.register(contextvars.ContextVar)
@choose_arg_getter_fn.register(ContextVarDescriptor)
def _getter_for_context_var(ctx_var: contextvars.ContextVar, **kwargs) -> GetterFn:
    def _get_ctxvar_value_or_default(default):
        try:
            return ctx_var.get()
        except LookupError:
            return default

    return _get_ctxvar_value_or_default


@choose_arg_getter_fn.register
def _getter_for_registry(registry: ContextVarsRegistry, name: str, **kwargs) -> GetterFn:
    return functools.partial(getattr, registry, name)
