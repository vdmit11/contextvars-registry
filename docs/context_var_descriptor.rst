module: context_var_descriptor
==============================

.. currentmodule:: contextvars_extras.context_var_descriptor

Overview
--------

.. contents::

.. rubric:: API Overview

.. rubric:: ContextVarDescriptor

.. autosummary::

   ContextVarDescriptor.__init__
   ContextVarDescriptor.from_existing_var
   ContextVarDescriptor.get
   ContextVarDescriptor.get_raw
   ContextVarDescriptor.is_set
   ContextVarDescriptor.set
   ContextVarDescriptor.set_if_not_set
   ContextVarDescriptor.reset
   ContextVarDescriptor.reset_to_default
   ContextVarDescriptor.delete

.. rubric:: Exceptions

.. autosummary::

   ContextVarNotSetError


class ContextVarDescriptor
--------------------------

:class:`ContextVarDescriptor` is an extension for the standard :class:`~contextvars.ContextVar` object,
that is designed to be placed in a class attribute, like this::

    >>> from contextvars_extras import ContextVarDescriptor

    >>> class MyVars:
    ...     locale = ContextVarDescriptor(default='en')

    >>> my_vars = MyVars()

When you place it inside a class, it starts to behave like a ``@property``.

That is, you just get/set object attributes, and under they hood they're translated
to method calls of the underlying :class:`contextvars.ContextVar` object::

    # calls ContextVar.get() under the hood
    >>> my_vars.locale
    'en'

    # calls ContextVar.set()
    >>> my_vars.locale = 'en_US'

    # calls ContextVar.get() again
    >>> my_vars.locale
    'en_US'

The underlying :class:`~contextvars.ContextVar` methods can be reached via class attributes::

    >>> MyVars.locale
    <ContextVarDescriptor name='__main__.MyVars.locale'>

    >>> MyVars.locale.get()
    'en_US'
    >>> token = MyVars.locale.set('en_GB')
    >>> MyVars.locale.get()
    'en_GB'
    >>> MyVars.locale.reset(token)
    >>> MyVars.locale.get()
    'en_US'


Inherited features of ContextVarExt
-----------------------------------

:class:`ContextVarDescriptor` is a subclass of :class:`~contextvars_extras.context_var_ext.ContextVarExt`.
That means that it supports extended features (not availble in the built-in :class:`contextvars.ContextVar`).

For example, you can delete the value::

    >>> class MyVars:
    ...     timezone = ContextVarDescriptor(default='UTC')

    >>> my_vars = MyVars()

    >>> my_vars.timezone
    'UTC'

    # the `del` operator erases the value stored in the context variable
    # (calls MyVars.timezone.delete() method under the hood)
    >>> del my_vars.timezone

    # now an attempt to access the attribute will throw AttributeError
    >>> try:
    ...     my_vars.timezone
    ... except AttributeError:
    ...     print('AttributeError was raised')
    AttributeError was raised

or, you can call extension methods,
like :meth:`~contextvars_extreas.context_var_ext.ContextVarExt.reset_to_default`::

  >>> MyVars.timezone.reset_to_default()

  >>> my_vars.timezone
  'UTC'

For details, visit the separate page dedicated to the base class:
:doc:`context_var_ext`


API reference
-------------

.. automodule:: contextvars_extras.context_var_descriptor
  :exclude-members: ContextVarDescriptor

  .. autoclass:: ContextVarDescriptor
    :special-members: __init__,__set_name__
    :inherited-members:
    :undoc-members:

     base class: :class:`contextvars_extras.context_var_ext.ContextVarExt`
