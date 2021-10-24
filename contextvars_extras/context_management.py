"""Tools for manual context management."""

import asyncio
from contextvars import Context, copy_context
from functools import partial, wraps
from typing import Callable, Coroutine, TypeVar

_ReturnT = TypeVar("_ReturnT")


def bind_to_snapshot_context(
    fn: Callable[..., _ReturnT], *args, **kwargs
) -> Callable[..., _ReturnT]:
    """Take a snapshot of all context variables, and produce a function bound to the snapshot.

    :returns: A modified function, that (on each call) restores context variables from the snapshot.

    It acts like :func:`functools.partial`, but in addition, it freezes all context variables
    to their current values. So the resulting function is always executed in a snapshot context.
    Moreover, each call of the resulting function obtains its own isolated snapshot,
    so you can call it multiple times safely.

    This is useful when you want to produce a "frozen" callback,
    protected from mutations of context variables, as illustrated in this example::

        >>> from contextvars_extras import ContextVarsRegistry
        >>> from contextvars_extras.context_management import bind_to_snapshot_context

        >>> class CurrentVars(ContextVarsRegistry):
        ...     user_id: int = None

        >>> current = CurrentVars()

        >>> def notify_current_user(message="some message"):
        ...     print(f"notify user_id={current.user_id}: {message}")

        >>> current.user_id = 1
        >>> callback = bind_to_snapshot_context(notify_current_user)

        # Callback is frozen, so modification of current.user_id doesn't affect the callback.
        >>> current.user_id = 2
        >>> callback()
        notify user_id=1: some message


    :func:`bind_to_snapshot_context` can be used in several ways:

      - with ``lambda: ...`` expression
      - with args/kwargs (then it acts like :func:`fucntools.partial`)
      - as a decorator

    All forms work in the same way, you can choose one that you like::

        >>> callbacks = []

        # Lambda form, no args/kwargs.
        >>> current.user_id = 1
        >>> callbacks.append(
        ...     bind_to_snapshot_context(lambda: notify_current_user(message="hello"))
        ... )

        # When args/kwargs passed, it acts like functools.partial()
        >>> current.user_id = 2
        >>> callbacks.append(
        ...     bind_to_snapshot_context(notify_current_user, message="hi")
        ... )

        # Can also be used as a decorator.
        >>> current.user_id = 42

        >>> @bind_to_snapshot_context
        ... def _callback():
        ...      notify_current_user(message="bonjour")

        >>> callbacks.append(_callback)

        # Execute accumulated callbacks.
        # The current context has mutated several times, but that doesn't affect callbacks,
        # because each callback has its own snapshot of all context variables.
        >>> for callback in callbacks:
        ...     callback()
        notify user_id=1: hello
        notify user_id=2: hi
        notify user_id=42: bonjour

    :func:`bind_to_snapshot_context` can also be helpful if you use threading
    or Gevent (green threads).

    The problem with threads (and greenlets in Gevent) is that they start in an empty context.
    That is, you lose values of all context variables whenever you decide to offload
    a function to background thread (or a Greenlet).

    This is illustrated by the example below::

        >>> from contextvars_extras import ContextVarsRegistry
        >>> from contextvars_extras.context_management import bind_to_snapshot_context

        >>> class CurrentVars(ContextVarsRegistry):
        ...     locale: str
        ...     timezone: str = 'UTC'

        >>> current = CurrentVars()

        >>> def print_current_vars():
        ...   print(dict(current))

        >>> current.locale = 'nb'
        >>> current.timezone = 'Antarctica/Troll'

        >>> print_current_vars()
        {'locale': 'nb', 'timezone': 'Antarctica/Troll'}

        # Run print_current_vars() in a background thread.
        # Changes made to context variables above are not visible from inside the Thread.
        # The Thread will see only default values, as if variables were never modified.
        >>> import threading
        >>> thread = threading.Thread(
        ...     target=print_current_vars
        ... )
        >>> thread.start()
        {'timezone': 'UTC'}

    This problem may be solved by wrapping your function with :func:`bind_to_snapshot_context`::

        >>> print_current_vars2 = bind_to_snapshot_context(print_current_vars)
        >>> thread = threading.Thread(
        ...     target=bind_to_snapshot_context(print_current_vars)
        ... )
        >>> thread.start()
        {'locale': 'nb', 'timezone': 'Antarctica/Troll'}

    It also works with Gevent in the same way::

        >>> import gevent

        # Normally, Gevent spawns greenlets in empty context.
        >>> greenlet = gevent.spawn(
        ...     print_current_vars
        ... )
        >>> greenlet.join()
        {'timezone': 'UTC'}

        # But, the context can be preserved by wrapping function with bind_to_snapshot_context()
        >>> greenlet = gevent.spawn(
        ...     bind_to_snapshot_context(print_current_vars)
        ... )
        >>> greenlet.join()
        {'locale': 'nb', 'timezone': 'Antarctica/Troll'}
    """
    # Use functools.partial() if args/kwargs passed.
    fn = _partial(fn, *args, **kwargs)

    snapshot_ctx = copy_context()

    @wraps(fn)
    def _wrapper__bind_to_snapshot_context(*arg, **kwargs) -> _ReturnT:
        # Each function call receives its own isolated copy of the snapshot.
        # This may not always be what you want, but this id done due to the Principle of Least
        # Astonishment: if you spawn N threads, you don't want them to have the shared context.
        snapshot_ctx_copy = snapshot_ctx.copy()

        return snapshot_ctx_copy.run(fn, *args, **kwargs)

    return _wrapper__bind_to_snapshot_context


def bind_to_empty_context(fn: Callable[..., _ReturnT], *args, **kwargs) -> Callable[..., _ReturnT]:
    """Bind function to empty context.

    :returns: A modified function, that always runs in an empty context,
              where all context variables take their default values.

    Example::

        >>> from contextvars_extras import ContextVarsRegistry
        >>> from contextvars_extras.context_management import bind_to_empty_context

        >>> class CurrentVars(ContextVarsRegistry):
        ...     locale: str
        ...     timezone: str = 'UTC'

        >>> current = CurrentVars()

        >>> def print_current_vars():
        ...     print(dict(current))

        >>> current.locale = 'nb'
        >>> current.timezone = 'Antarctica/Troll'

        >>> print_current_vars()
        {'locale': 'nb', 'timezone': 'Antarctica/Troll'}

        >>> print_current_vars_in_empty_context = bind_to_empty_context(print_current_vars)
        >>> print_current_vars_in_empty_context()
        {'timezone': 'UTC'}

    This may be useful if you want to "simulate" an empty state.

    Like, for example, when you have an HTTP server, you sometimes want to build a "proxy" API,
    that does a nested call to another API endpoint (or even multiple endpoints) which usually start
    in empty context, but you call it in an existing API context, and that leads to a conflict.

    To solve the problem, you may wrap nested API calls with :func:`bind_to_to_empty_context`,
    and then they will be called in empty context, as if there was no parent API call.
    """
    # Use functools.partial() if args/kwargs passed.
    fn = _partial(fn, *args, **kwargs)

    @wraps(fn)
    def _wrapper__bind_to_empty_context(*args, **kwargs) -> _ReturnT:
        empty_context = Context()
        return empty_context.run(fn, *args, **kwargs)

    return _wrapper__bind_to_empty_context


def bind_to_sandbox_context(
    fn: Callable[..., _ReturnT], *args, **kwargs
) -> Callable[..., _ReturnT]:
    """Modify function to copy context on each call.

    :returns: a modified function, that copies context on each call.

    This tool allows you to put a function into an isolated sandbox,
    where it can change context varaibles freely, without affecting the caller.

    Changes made to context variables will be visible only inside the function call.
    Once the function returns, all context variables are automatically restored to previous values.

    Example::

        >>> from contextvars_extras import ContextVarsRegistry
        >>> from contextvars_extras.context_management import bind_to_sandbox_context

        >>> class CurrentVars(ContextVarsRegistry):
        ...     timezone: str = 'UTC'

        >>> current = CurrentVars()

        >>> def print_current_vars():
        ...     print(dict(current))

        >>> @bind_to_sandbox_context
        ... def modify_and_print_current_vars():
        ...     current.timezone = 'Antarctica/Troll'
        ...     current.locale = 'en_US'
        ...     print_current_vars()


        >>> current.timezone = 'GMT'

        >>> print_current_vars()
        {'timezone': 'GMT'}

        >>> modify_and_print_current_vars()
        {'timezone': 'Antarctica/Troll', 'locale': 'en_US'}

        >>> print_current_vars()
        {'timezone': 'GMT'}

    This is useful for batch processing, where you run N jobs in sequence, and you want to
    put each job to a sandbox, where it can set context variables without affecting other jobs.

    This is also useful for unit tests, where you need to isolate tests from each other.
    Just decorate test with ``@bind_to_sandbox_context``, and then all changes made to context
    variables become local to the test.
    """
    # Use functools.partial() if args/kwargs passed.
    fn = _partial(fn, *args, **kwargs)

    @wraps(fn)
    def _wrapper__bind_to_sandbox_context(*args, **kwargs) -> _ReturnT:
        sandbox_context = copy_context()
        return sandbox_context.run(fn, *args, **kwargs)

    return _wrapper__bind_to_sandbox_context


def _partial(fn: Callable[..., _ReturnT], *args, **kwargs) -> Callable[..., _ReturnT]:
    # This function behaves like functools.partial(),
    # except that it does NOT apply partial() and returns function as-is if no arguments provided.
    #
    # This is is done to make debugging slightly more nice: The original function (without partial)
    # just looks better in stack traces and print() statements.
    #
    # Also, there is a performance improvement, but it is minor, and can be neglected.
    if args or kwargs:
        fn = partial(fn, *args, **kwargs)
    return fn


def create_async_task_in_empty_context(coro: Coroutine) -> asyncio.Task:
    """Create asyncio Task in empty context (where all context vars are set to default values).

    By default, :mod:`asyncio` copies context whenever you create a new :class:`asyncio.Task`.
    So, each Task inherits context variables from its parent Task.

    This may not always be what you want.
    Sometimes, you want to start a Task with an empty context.
    So this :func:`create_async_task_in_empty_context` helper allows you to do that.

    You just replace :func:`asyncio.create_task` with :func:`create_async_task_in_empty_context`,
    and you're done. The new task will ignore parent's context, and start with an empty context
    (where all context context variables will take their default values).

    Example::

        >>> from asyncio import create_task, run
        >>> from contextvars_extras import ContextVarsRegistry
        >>> from contextvars_extras.context_management import create_async_task_in_empty_context

        >>> class CurrentVars(ContextVarsRegistry):
        ...     locale: str = 'en'
        ...     timezone: str = 'UTC'

        >>> current = CurrentVars()

        >>> async def print_current_vars():
        ...     print(dict(current))

        >>> async def main():
        ...     current.locale = 'nb'
        ...     current.timezone = 'Antarctica/Troll'
        ...
        ...     # Normally, if you call asyncio.create_task(), it copies the current context.
        ...     # So, this print_current_vars() below should see locale/timezone values set above.
        ...     await create_task(
        ...         print_current_vars()
        ...     )
        ...
        ...     # But, if you use create_async_task_in_empty_context(), the new task will start with
        ...     # an empty context (all context variables will take their default values).
        ...     # So, print_current_vars() below should get only default values.
        ...     await create_async_task_in_empty_context(
        ...         print_current_vars()
        ...     )

        >>> run(main())
        {'locale': 'nb', 'timezone': 'Antarctica/Troll'}
        {'locale': 'en', 'timezone': 'UTC'}
    """
    empty_context = Context()
    task = empty_context.run(asyncio.create_task, coro)
    return task
