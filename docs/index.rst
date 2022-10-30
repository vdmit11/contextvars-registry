contextvars-extras
==================

:mod:`contextvars-extras` is a set of extensions for the Python's :mod:`contextvars` module.

In case you're not familiar with Context Variables, they're sort of `Thread Local Storage`_
that works not only with :mod:`threading`, but also other concurrency mechanisms,
like :mod:`asyncio` and :mod:`gevent`.

.. _`Thread Local Storage`: https://stackoverflow.com/questions/104983/what-is-thread-local-storage-in-python-and-why-do-i-need-it

That is, for example, if you have a web application, it is often handy to have a bunch of
"current" variables, like: "current URL", or "current user ID", or "current DB connection".

So :class:`contextvars.ContextVar` allows to store this kind of "current" values in a thread-safe way:
each :class:`~threading.Thread` gets its own isolated context, where it can set context variables freely,
without interfering with other threads (and the same is true for :class:`asyncio.Task` and
:class:`gevent.Greenlet` - each of them runs in its own isolated context).

Ok, then what is wrong with the standard :mod:`contextvars` module?
Why do you also need a 3rd-party library?

Well, technically, nothing is wrong. The standard :mod:`contextvars` module works fine,
but its API is too minimalist, if not primitive. "Batteries included" principle
somehow not applies there.

So this :mod:`contextvars-extras` package supplies the batteries.
It is just adds some higher-level nice-to-have tools on top of the standard :mod:`contextvars`.

The two main concepts provided are:

:doc:`class ContextVarsRegistry <context_vars_registry>` - provides nice ``@property``-like
access to context variables. You just get/set its attributes, and the underlying
:class:`~contextvars.ContextVar` objects are managed automatically under the hood.

:doc:`class ContextVarExt <context_var_ext>` - a wrapper and drop-in replacement to the standard
:class:`~contextvars.ContextVar`, that adds some extra methods and features. You can use it
if you like extra features, but don't like the registry magic.

There are other things, that aren't that bold, but hopefully still useful.

Check out the modules, listed below.

Pages
-----

.. toctree::
   :maxdepth: 1

   context_vars_registry
   context_var_ext
   context_var_descriptor
   context_management
   integrations.wsgi


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
