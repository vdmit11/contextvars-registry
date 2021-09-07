extra docs for Python's contextvars
===================================

This page contains some notes about the standard :mod:`contextvars` module,
about classic :class:`contextvars.ContextVar` objects (without any extensions
from this ``contextvars-extras`` package).

Just some common misconceptions and recipes that are missing in the official docs.

ContextVar default
------------------

The ``default`` value (one that you pass to :class:`contextvars.ContextVar` constructor)
may sometimes be counter-intuitive, especially if you're implementing functions like
``get_value`` and ``has_value()`` shown below:

.. code-block::
   :name: example of odd ContextVar default behavior

   >>> from contextvars import ContextVar

   >>> Missing = object()

   >>> def get_value(context_var: ContextVar, default=Missing):
   ...     """Get value of ContextVar, avoiding LookupError if the value is missing."""
   ...     value = context_var.get(default)
   ...     if value is Missing:
   ...          return None
   ...     return value

   >>> def has_value(context_var: ContextVar) -> bool:
   ...     value = context_var.get(Missing)
   ...     return value is not Missing

   >>> timezone_var = ContextVar('timezone_var', default='UTC')

   # Looks like the ContextVar has value
   >>> timezone_var.get()
   'UTC'

   # ...but my has_value()/get_value() functions think that there is no value
   >>> has_value(timezone_var)
   False
   >>> get_value(timezone_var)  # returns None


The misconception here is that the *default* value is not the *initial* value.

That is, the created :class:`contextvars.ContextVar` remains unset uninitialized,
even if you provide a ``default`` value. It remains unitialized until you call the
:meth:`contextvars.ContextVar.set` method, check this out:

.. code-block::
   :name: ContextVar remains unitialized even if you provide a default value

   >>> from contextvars import copy_context

   # the context variable is not set, even though there is a default value
   >>> context = copy_context()
   >>> context[timezone_var]
   Traceback (most recent call last):
   ...
   KeyError: <ContextVar name='timezone_var' default='UTC' ...>

   # call the .set() method, and the variable now really has a value set
   >>> timezone_var.set('UTC')
   <Token ...>

   >>> context = copy_context()
   >>> context[timezone_var]
   'UTC'

The trick is that the ``default`` value in ``ContextVar(default=...)`` is not really
a value for the context variable. The variable is never set to the ``default`` value.

Instead, the ``default`` in ``ContextVar(default=...)`` acts a default argument for the
:meth:`contextvars.ContextVar.get` method.

If you percept it this way, it becomes clear why the default value for ``.get(default)`` call
outshadows the default value that was passed to the ``ContextVar(default=...)`` constructor.

So, how do you deal with that if you want to implement functions like ``get_value()``
and ``has_value()`` from the example above?

The answer is simple: don't pass the argument to the ``.get()`` call.

Instead, utilize ``LookupError``, as shown in these recepies:

 - `Get value from ContextVar, avoiding LookupError`_
 - `Check if ContextVar has a value`_





Recipes
-------

Get value from ContextVar, avoiding LookupError
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

   >>> from contextvars import ContextVar

   >>> def get_context_var_value(context_var: ContextVar, default=None):
   ...     """Get value of a ContextVarm, avoiding LookupError if the value is missing."""
   ...     try:
   ...         return context_var.get()
   ...     except LookupError:
   ...         return default

   >>> timezone_var_with_default = ContextVar('timezone_var', default='UTC')
   >>> timezone_var_without_default = ContextVar('timezone_var')

   >>> get_context_var_value(timezone_var_with_default)
   'UTC'

   >>> get_context_var_value(timezone_var_with_default, default=None)
   'UTC'

   >>> get_context_var_value(timezone_var_without_default)  # returns None

   >>> get_context_var_value(timezone_var_without_default, default='Antarctica/Troll')
   'Antarctica/Troll'

Check if ContextVar has a value
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

   >>> from contextvars import ContextVar

   >>> def context_var_has_value(context_var: ContextVar) -> bool:
   ...     try:
   ...         context_var.get()
   ...     except LookupError:
   ...         return False
   ...     else:
   ...         return True

   >>> timezone_var_with_default = ContextVar('timezone_var', default='UTC')
   >>> timezone_var_without_default = ContextVar('timezone_var')

   >>> context_var_has_value(timezone_var_with_default)
   True

   >>> context_var_has_value(timezone_var_without_default)
   False

   >>> timezone_var_without_default.set('CEST')
   <Token ...>

   >>> context_var_has_value(timezone_var_without_default)
   True

Get the default value from ContextVar object
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code:: python

   >>> from contextvars import ContextVar, Context

   >>> def get_context_var_default(context_var: ContextVar, _empty_context=Context()):
   ...     try:
   ...         return _empty_context.run(context_var.get)
   ...     except LookupError:
   ...         return None

   >>> timezone_var_with_default = ContextVar('timezone_var', default='UTC')
   >>> timezone_var_without_default = ContextVar('timezone_var')

   >>> timezone_var_with_default.set('CEST')
   <Token ...>

   >>> timezone_var_without_default.set('CEST')
   <Token ...>

   >>> get_context_var_default(timezone_var_with_default)
   'UTC'

   >>> get_context_var_default(timezone_var_without_default)  # returns None
