from contextvars_extras.descriptor import ContextVarValueDeleted
from contextvars_extras.registry import ContextVarsRegistry


def save_context_vars_registry(registry: ContextVarsRegistry) -> dict:
    """Dump variables from ContextVarsRegistry as dict.

    The resulting dict can be used as argument to :func:`restore_context_vars_registry`.
    """
    # pylint: disable=protected-access
    return {key: descriptor.get_raw() for key, descriptor in registry._var_descriptors.items()}


def restore_context_vars_registry(registry: ContextVarsRegistry, saved_registry_state: dict):
    """Restore ContextVarsRegistry state from dict.

    The :func:`restore_context_vars_registry` restores state of :class:`ContextVarsRegistry`,
    using state that was previously dumped by :func:`save_context_vars_registry`.

    :param registry: a :class:`ContextVarsRegistry` instance that will be written
    :param saved_registry_state: output of :func:`save_context_vars_registry` function

    Example::

        >>> from contextvars_extras.registry import ContextVarsRegistry
        >>> from contextvars_extras.registry_restore import (
        ...    save_context_vars_registry,
        ...    restore_context_vars_registry,
        ... )

        >>> class CurrentVars(ContextVarsRegistry):
        ...     locale: str = 'en'
        ...     timezone: str = 'UTC'

        >>> current = CurrentVars()
        >>> state1 = save_context_vars_registry(current)

        >>> current.locale = 'en_US'
        >>> current.timezone = 'America/New York'
        >>> state2 = save_context_vars_registry(current)

        >>> del current.locale
        >>> del current.timezone
        >>> current.user_id = 42
        >>> state3 = save_context_vars_registry(current)

        >>> restore_context_vars_registry(current, state1)
        >>> dict(current)
        {'locale': 'en', 'timezone': 'UTC'}

        >>> restore_context_vars_registry(current, state2)
        >>> dict(current)
        {'locale': 'en_US', 'timezone': 'America/New York'}

        >>> restore_context_vars_registry(current, state3)
        >>> dict(current)
        {'user_id': 42}

    A similar result could be achieved by the standard :class:`collections.abc.MutableMapping`
    methods, like ``registry.clear()`` and ``registry.update()``, but this is not exactly the same.
    There is still a couple of differences:

      1. :func:`save_registry_state` and :func:`restore_registry_state` can handle special cases,
         like ``ContextVarValueDeleted`` tokens, or lazy initializers.

      2. :class:`collections.abc.MutableMapping` methods are slow, while
         :func:`save_registry_state` and :func:`restore_registry_state` are faster,
         since they can reach some registry internals directly, avoiding complex methods.

    .. Note::

        This function is not scalable, it takes O(N) time, where N is the number of variables
        in the registry.

        There is a faster tool, a decorator that saves/restores all context variables on each call,
        and that takes O(1) time: :func:`contextvars_extras.context.bind_to_sandbox_context`

        So you prefer that decorator by default, and choose :func:`restore_registry_state`
        only when you can't use the decorator, or when you need to restore only 1 specific
        registry, not touching variables outside of the registry.
    """
    get_saved_value = saved_registry_state.get

    # pylint: disable=protected-access
    for key, descriptor in registry._var_descriptors.items():
        descriptor.set(get_saved_value(key, ContextVarValueDeleted))
