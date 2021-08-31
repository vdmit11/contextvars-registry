README
======

**Warning! The code is at the early development stage, and may be unstable. Use with caution.**

contextvars-extras is a set of extensions for the Python's `contextvars`_ module.

.. _contextvars: https://docs.python.org/3/library/contextvars.html
.. _ContextVar: https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar

In case you're not familiar with the standard `contextvars`_ module,
it allows you to create `ContextVar`_ objects, like this::

  timezone_var = ContextVar('timezone_var')
  timezone_var.set('UTC')
  timezone_var.get()  # => 'UTC'

The point here is that these variables are thread-safe and async-safe
(they can act as both thread-local storage and async task-local storage out of the box).

`contextvars`_ is a good package, but its API seem too low-level.

So this `contextvars_extras` provides some higher-level additions on top of the standard API.

Here is a brief overview of them...


ContextVarsRegistry
-------------------

``ContextVarsRegistry`` provides nice ``@property``-like access to `ContextVar`_ objects:

You just get/set object attributes, and under the hood these operations are translated
to `ContextVar.get()`_ and `ContextVar.set()`_ calls:

.. code:: python

  from contextvars_extras.registry import ContextVarsRegistry

  class CurrentVars(ContextVarsRegistry):
      timezone: str = 'UTC'

  current = CurrentVars()

  # calls ContextVar.get() under the hood
  current.timezone  # => 'UTC'

  # calls ContextVar.set() under the hood
  current.timezone = 'GMT'

  # ContextVar() objects can be reached as lass members
  CurrentVars.timezone.get()  # => 'GMT'

.. _ContextVar.get(): https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar.get
.. _ContextVar.set(): https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar.set
  
It has a lot of other features (check out the docs), but the nicest thing is that it just makes
your code more readable (no more noisy ``.get()`` calls), and it naturally firendly to `typing`_,
so you get auto-completion and other helpful features of your IDE.


Injecting Function Arguments
----------------------------

``@inject_vars`` decorator passes values of context variables as function arguments:

.. code:: python

  form contextvars_extras.registry import ContextVarsRegistry
  from contextvars_extras.inject import inject_vars

  class CurrentVars(ContextVarsRegistry):
      locale: str = 'en'
      timezone: str = 'UTC'
      user_id: int

  current = CurrentVars()

  @inject_vars(current)
  def get_values(user_id=None, locale=None, timezone=None):
      return (user_id, locale, timezone)

  # Missing arguments are filled in from context variables.
  get_values()  # => (None, 'en', 'UTC')

  # Setting the context variable affects the function.
  current.user_id = 42
  get_values()  # => (42, 'en', 'UTC')

  # Arguments can also be passed manually (that "overrides" context variables).
  get_values(locale='en_GB' timezone='GMT', user_id=None)  # => (None, 'en_GB', 'GMT')

This is useful for passing arguments deeply along the call stack.

Have you ever experienced a need of passing some minor thing, like the "current timezone"
to some low-level deeply nested function? Like yeah, you could just pass it as an argument,
but it turns out that you need to modify like 30 parent functions, and some of them are located
in 3-rd party packages... Know that feeling, huh?
So then ``@inject_vars`` could help you to solve the problem.

``@inject_vars`` also can get values from different sources: registries, classic `ContextVar`_ objects,
custom ``lambda: ...`` expressions, and more. Check out its docs for more information.


more docs 
---------

Read the Docs: https://contextvars-extras.readthedocs.io/en/latest/

.. image:: https://readthedocs.org/projects/contextvars-extras/badge/?version=latest
  :target: https://contextvars-extras.readthedocs.io/en/latest/?badge=latest
  :alt: Documentation Status
