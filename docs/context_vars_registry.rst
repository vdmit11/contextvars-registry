module: context_vars_registry
=============================

.. currentmodule:: contextvars_extras.context_vars_registry

ContextVarsRegistry - a nice ``@property``-like way to access context variables.

Overview
--------

.. contents::


.. rubric:: API Overview

.. rubric:: class ContextVarsRegistry

.. autosummary::

   ContextVarsRegistry._registry_auto_create_vars
   ContextVarsRegistry.__call__


.. rubric:: Functions

.. autosummary::
   restore_context_vars_registry
   save_context_vars_registry


.. rubric:: Exceptions

.. autosummary::

   RegistryInheritanceError
   ReservedAttributeError
   UndeclaredAttributeError


class ContextVarsRegistry
-------------------------

The idea is simple: you create a sub-class, and declare your variables using type annotations:

    >>> from contextvars_extras import ContextVarsRegistry

    >>> class CurrentVars(ContextVarsRegistry):
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
    <ContextVarDescriptor name='__main__.CurrentVars.timezone'>

and its underlying ContextVar can be reached via the `.context_var` attribute:

    >>> CurrentVars.timezone.context_var
    <ContextVar name='__main__.CurrentVars.timezone'...>

But in practice, you normally shouldn't need that.
ContextVarDescriptor should implement all same attributes and methods as ContextVar,
and thus it can be used instead of ContextVar() object in all cases except isinstance() checks.


dict-like access
^^^^^^^^^^^^^^^^

:class:`ContextVarsRegistry` implements MutableMapping_ protocol.

.. _MutableMapping:
   https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping

That means that you can get/set context variables, as if it was just a ``dict``, like this::

    >>> current['locale'] = 'en_US'
    >>> current['locale']
    'en_US'

Standard dict operators are supported::

    # `in` operator
    >>> 'locale' in current
    True

    # count variables in the dict
    >>> len(current)
    3

    # iterate over keys in the dict
    >>> for key in current:
    ...     print(key)
    locale
    timezone
    user_id

    # convert to dict() easily
    >>> dict(current)
    {'locale': 'en_US', 'timezone': 'UTC', 'user_id': None}

Other ``dict`` methods are supported as well::

    >>> current.update({
    ...    'locale': 'en',
    ...    'timezone': 'UTC',
    ...    'user_id': 42
    ... })

    >>> current.keys()
    dict_keys(['locale', 'timezone', 'user_id'])

    >>> current.values()
    dict_values(['en', 'UTC', 42])

    >>> current.pop('locale')
    'en'

    >>> current.items()
    dict_items([('timezone', 'UTC'), ('user_id', 42)])


deleting attributes
^^^^^^^^^^^^^^^^^^^

In Python, it is not possible to delete a ``ContextVar`` object.
(well, technically, it could be deleted, but that leads to a memory leak, so we forbid deletion).

So, we have to do some trickery to implement deletion...

When you call ``del`` or ``delattr()``, we don't actually delete anything,
but instead we write to the variable a special token object called ``ContextVarValueDeleted``.

Later on, when the variable is read, there is a ``if`` check under the hood,
that detects the special token and throws an exception.

On the high level, you should never notice this hack.
Attribute mechanics works as expected, as if the attribute is really deleted, check this out::


    >>> hasattr(current, 'user_id')
    True

    >>> delattr(current, 'user_id')

    >>> hasattr(current, 'user_id')
    False

    >>> try:
    ...     current.user_id
    ... except AttributeError:
    ...     print("AttributeError raised")
    ... else:
    ...     print("not raised")
    AttributeError raised

    >>> getattr(current, 'user_id', 'DEFAULT_VALUE')
    'DEFAULT_VALUE'

...but if you try to use :meth:`~.ContextVarDescriptor.get_raw` method,
you will get that special ``ContextVarValueDeleted`` object stored in the ``ContextVar``::

    >>> CurrentVars.user_id.get_raw()
    contextvars_extras.context_var_ext.ContextVarValueDeleted

So, long story short: once allocated, a ``ContextVar`` object lives forever in the registry.
When you delete it, we only mark it as deleted, but never actually delete it.
All this thing happens under the hood, and normally you shouln't notice that.


ContextVarsRerigsty API reference
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: contextvars_extras.context_vars_registry.ContextVarsRegistry


other members of the module
---------------------------

.. automodule:: contextvars_extras.context_vars_registry
  :exclude-members: ContextVarsRegistry
