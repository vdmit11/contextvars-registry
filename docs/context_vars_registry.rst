module: context_vars_registry
=============================

This is documentation page for the module: :mod:`contextvars_extras.context_vars_registry`

The module is about `class ContextVarsRegistry`_ - a container that provides nice
``@property``-like access to context variables.

.. contents:: Contents
   :local:

.. currentmodule:: contextvars_extras.context_vars_registry

API summary
-----------

.. rubric:: `class ContextVarsRegistry`_

.. autosummary::

   ContextVarsRegistry._registry_allocate_on_setattr
   ContextVarsRegistry.__call__


.. rubric:: Functions

.. autosummary::
   restore_context_vars_registry
   save_context_vars_registry


.. rubric:: Exceptions

.. autosummary::

   RegistryInheritanceError
   SetClassVarAttributeError


class ContextVarsRegistry
-------------------------

:class:`ContextVarsRegistry` is a container that makes context variables behave like ``@property``.

The idea is simple: you create a sub-class, and just declare some attributes::

    >>> from contextvars_extras import ContextVarsRegistry

    >>> class CurrentVars(ContextVarsRegistry):
    ...    locale: str = 'en_GB'
    ...    timezone: str = 'Europe/London'
    ...    user_id: int = None
    ...    db_session: object

    >>> current = CurrentVars()

so then all these attributes become context variables, and you can work with them
by just getting/setting attributes::

    >>> current.locale
    'en_GB'

    >>> current.timezone
    'Europe/London'

    >>> current.timezone = 'UTC'
    >>> current.timezone
    'UTC'

Getting/setting an attribute is automatically mapped to
:meth:`~contextvars.ContextVar.get`/:meth:`~contextvars.ContextVar.set` methods
of the underlying :class:`~contextvars.ContextVar` object.

The underlying :class:`contextvars.ContextVar` can be reached via class attributes::

    >>> CurrentVars.timezone.get()
    'UTC'

    >>> token = CurrentVars.timezone.set('GMT')
    >>> current.timezone
    'GMT'
    >>> CurrentVars.timezone.reset(token)
    >>> current.timezone
    'UTC'

Well, actually, the above is a little lie: the class members are not quite context variables,
they're really instances of :class:`~contextvars_extras.context_var_descriptor.ContextVarDescriptor`.

    >>> CurrentVars.timezone
    <ContextVarDescriptor name='__main__.CurrentVars.timezone'>

:class:`~contextvars_extras.context_var_descriptor.ContextVarDescriptor` has all the standard
:meth:`~contextvars_extras.context_var_descriptor.ContextVarDescriptor.get`/
:meth:`~contextvars_extras.context_var_descriptor.ContextVarDescriptor.set`/
:meth:`~contextvars_extras.context_var_descriptor.ContextVarDescriptor.reset`
methods, but it is not a subclass of :class:`~contextvars.ContextVar` (because it
cannot be subclassed, it is just a technical limitation).

if you really need to reach the low-level :class:`~contextvars.ContextVar` object,
then you just use the ``.context_var`` attribute::

    >>> CurrentVars.timezone.context_var
    <ContextVar name='__main__.CurrentVars.timezone'...>

But in most cases, you don't need it, because
:class:`~contextvars_extras.context_var_descriptor.ContextVarDescriptor` implements all the same
methods an attributes as the standard :class:`~contextvars.ContextVar`, so it would work
as a drop-in replacement in all cases except :func:`isinstance` checks.


dict-like Access
----------------

:class:`ContextVarsRegistry` implements :class:`collections.abc.MutableMapping` protocol.

That means that you can get/set context variables, as if it was just a :class:`dict`, like this::

    >>> current['locale'] = 'en_US'
    >>> current['locale']
    'en_US'

Standard :class:`dict` operators are supported::

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

Methods are supported as well::

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


Deleting Attributes
-------------------

In Python, it is not possible to delete a :class:`~contextvars.ContextVar` object.
(an attempt to do so causes a memory leak, so you shall never really delete context variables).

So, we have to do some trickery to implement deletion...

When you call ``del`` or :func:`delattr`, we don't actually delete anything,
but instead we write to the variable a special sentinel object called
:data:`~contextvars_extras.context_var_ext.DELETED`.

Later on, when the variable is read, there is a ``if`` check under the hood,
that detects the special sentinel object, and throws an exception.

On the high level, you should never notice this trick.
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

The only case when you see this special :data:`~contextvars_extras.context_var_ext.DELETED` object
is when you use some low-level stuff, like :func:`save_context_vars_registry`, or
the :meth:`~.ContextVarDescriptor.get_raw` method::

    >>> CurrentVars.user_id.get_raw()
    <DELETED>

So, long story short: once a :class:`contextvars.ContextVar` object is allocated,
it lives forever in the registry.
When you delete it, we only mark it as deleted, but never actually delete it.
All this thing happens under the hood, and normally you shouln't notice it.




Which attributes become context variables?
------------------------------------------

When subclassed, :class:`ContextVarsRegistry` automatically converts its attributes
to context variables.

But, not all attributes should become context variables.
For example, you may want to define some methods, and you probably don't expect
them to become context variables.

So, how does :class:`ContextVarsRegistry` know which attributes should be converted
to context vars, and which attributes should be skipped?

The rules are the following:

- For attributes with type hints, things are simple and explicit: 

  * if you add :data:`~typing.ClassVar`, then attribute is skipped
  * otherwise it is converted to context variables

- Without type hints, things become a bit more complicated:

  * skipped:

    * methods (regular functions defined via ``def``)
    * :class:`@property` (and other kinds of descriptors)
    * special attributes (like :data:`__doc__`)

  * all other attributes are converted to context variables
    (including: :ref:`lambda`, :func:`~functools.partial` and custom :func:`callable` objects
    - they're all converted to context variables)

Here is an example of how these rules are applied::

  >>> from typing import ClassVar

  >>> class CurrentVars(ContextVarsRegistry):
  ...   # ClassVar attributes are skipped
  ...   hinted_with_class_var: ClassVar[str] = "class variable"
  ...
  ...   # other attributes are wrapped with ContextVarDescriptor
  ...   hinted_with_int: int
  ...   hinted_with_str: str = "default value"

  >>> CurrentVars.hinted_with_class_var
  'class variable'

  >>> CurrentVars.hinted_with_int
  <ContextVarDescriptor name='....CurrentVars.hinted_with_int'>

  >>> CurrentVars.hinted_with_str
  <ContextVarDescriptor name='....CurrentVars.hinted_with_str'>

  >>> CurrentVars.hinted_with_str.get()
  'default value'


and without type hints::

  >>> from functools import partial

  >>> class CurrentVars(ContextVarsRegistry):
  ...     # All regular attributes are converted to context variables
  ...     # (even "private" attributes are converted!).
  ...     var1 = "var1 default value"
  ...     _var2 = "var2 default value"
  ...     __var3 = "var3 default value"
  ...
  ...     # special attributes are skipped
  ...     __special__ = "special attribute"
  ...
  ...     # properties are skipped
  ...     @property
  ...     def some_property(self):
  ...         return self.__var3
  ...
  ...     # Methods are skipped.
  ...     def some_method(self):
  ...         return self.__var3
  ...
  ...     # BUT: lambda/partial functions are converted to context variables!
  ...     some_lambda = lambda self: self.var1
  ...     some_partial = partial(some_method)

  # All regular attributes are converted to context variables.
  >>> CurrentVars.var1
  <ContextVarDescriptor ...>

  # Even "private" attributes are converted.
  >>> CurrentVars._CurrentVars__var3
  <ContextVarDescriptor ...>

  # @properties are skipped
  >>> CurrentVars.some_property
  <property object ...>

  # Methods are skipped.
  >>> CurrentVars.some_method
  <function CurrentVars.some_method ...>

  # BUT: lambda functions are converted!
  >>> CurrentVars.some_lambda
  <ContextVarDescriptor ...>

  # partial() objects are also converted
  >>> CurrentVars.some_partial
  <ContextVarDescriptor ...>

So, as you can see, without type annotations rules become tricky, somewhat magic,
sometimes even fragile.

Like, for example, you may apply a decorator to your method, and the decorator
returns a :func:`~functools.partial` object, and then your method suddenly
becomes a :class:`ContextVarDescriptor`, which wasn't your intent.

To avoid such surprises, just always add type hints. They make things safe and explicit.

API reference
-------------

.. automodule:: contextvars_extras.context_vars_registry
   :special-members: __call__
   :private-members: _registry_allocate_on_setattr
