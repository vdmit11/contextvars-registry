from asyncio import Task, create_task
from contextvars import Context
from typing import Coroutine


def create_task_in_empty_context(coro: Coroutine) -> Task:
    """Create asyncio Task in empty context (where all context vars are set to default values).

    By default, :ref:`asyncio` copies context whenever you create a new :class:`asyncio.Task`.
    So, each Task inherits context variables from its parent Task.

    This may not always be what you want.
    Sometimes, you want to start a Task with an empty context.
    So this :func:`create_task_in_empty_context` helper allows you to do that.

    You just replace :func:`asyncio.create_task` with :func:`create_task_in_empty_context`,
    and you're done. The new task will ignore parent's context, and start with an empty context
    (where all context context variables will take their default values).

    Example::

        >>> from asyncio import create_task, run
        >>> from contextvars_extras.registry import ContextVarsRegistry
        >>> from contextvars_extras.context_async import create_task_in_empty_context

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
        ...     # But, if you use create_task_in_empty_context(), the new task will start with
        ...     # an empty context (all context variables will take their default values).
        ...     # So, print_current_vars() below should get only default values.
        ...     await create_task_in_empty_context(
        ...         print_current_vars()
        ...     )

        >>> run(main())
        {'locale': 'nb', 'timezone': 'Antarctica/Troll'}
        {'locale': 'en', 'timezone': 'UTC'}
    """
    empty_context = Context()
    task = empty_context.run(create_task, coro)
    return task
