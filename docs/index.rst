contextvars-registry
====================

:mod:`contextvars_registry` is an extension for the Python's :mod:`contextvars` module.

In case you're not familiar with Context Variables, they work like `Thread Local Storage`_,
but better:

- Context variables are both thread-safe and async task-safe (work seamlessly across :mod:`threading`, :mod:`asyncio`, :mod:`gevent`, and probably other concurrency mechanisms).
- Cheap snapshots: **all** variables are copied at once in O(1) time (and then you can :meth:`~contextvars.Context.run` a function in the copied isolated context).

.. _`Thread Local Storage`: https://stackoverflow.com/questions/104983/what-is-thread-local-storage-in-python-and-why-do-i-need-it

The Python's :mod:`contextvars` is a powerful module, but its API seems too low-level.

So this :mod:`contextvars_registry` package provides some higher-level additions on top of the
standard API. Most notably, it allows to group :class:`~contextvars.ContextVar` objects
in a registry class with ``@property``-like access:

.. code:: python

    from contextvars_registry import ContextVarsRegistry

    class CurrentVars(ContextVarsRegistry):
        locale: str = 'en'
        timezone: str = 'UTC'

    current = CurrentVars()

    # calls ContextVar.get() under the hood
    current.timezone  # => 'UTC'

    # calls ContextVar.set() under the hood
    current.timezone = 'GMT'

    # ContextVar() methods can be reached via class members
    CurrentVars.timezone.get()  # => 'GMT'


That makes your code more readable (no more noisy ``.get()`` calls),
and it is naturally friendly to :mod:`typing`, so static code analysis features
(like type checkers and auto-completion in your IDE) work nicely.


Pages
-----

.. toctree::
   :maxdepth: 1

   context_vars_registry
   context_var_descriptor
   context_management
   integrations.wsgi


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
