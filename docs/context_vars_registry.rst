module: context_vars_registry
=============================

This is documentation page for the module: :mod:`contextvars_registry.context_vars_registry`

The module is about `class ContextVarsRegistry`_ - a container that provides nice
``@property``-like access to context variables.

.. contents:: Contents
   :local:

.. currentmodule:: contextvars_registry.context_vars_registry

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

The idea is simple: you create a sub-class, and its attributes magically become context variables::

    >>> from contextvars_registry import ContextVarsRegistry

    >>> class CurrentVars(ContextVarsRegistry):
    ...    locale: str = "en"
    ...    timezone: str = "UTC"
    ...    user_id: int = None
    ...    db_session: object

    >>> current = CurrentVars()

and then you can work with context variables by just getting/setting the attributes::

    >>> current.timezone  # ContextVar.get() is called under the hood
    'UTC'

    >>> current.timezone = "GMT"  # ContextVar.set() is called under the hood
    >>> current.timezone
    'GMT'

The underlying :class:`~contextvars.ContextVar` methods can be reached via class members::

    >>> CurrentVars.timezone.get()
    'GMT'

    >>> token = CurrentVars.timezone.set("Europe/London")
    >>> current.timezone
    'Europe/London'
    >>> CurrentVars.timezone.reset(token)
    >>> current.timezone
    'GMT'


Descriptors
-----------

An important thing to understand is that :class:`ContextVarsRegistry` is not a classic Python object.
It doesn't have any instance state, and you cannot really mutate its attributes.
All its attributes are "virtual" proxies to context variables.

That is, when you're setting an attribute like this::

    current.timezone = "GMT"

Under the hood it really turns into this::

    CurrentVars.timezone.set("GMT")

The ``CurrentVars.timezone`` above is a magic
:class:`~contextvars_registry.context_var_descriptor.ContextVarDescriptor` object,
check this out::

    >>> CurrentVars.timezone
    <ContextVarDescriptor name='__main__.CurrentVars.timezone'...>

Such :class:`~contextvars_registry.context_var_descriptor.ContextVarDescriptor` is an
extended version of the standard :class:`contextvars.ContextVar` that behaves like ``@property``
when you put it into a class.

Another important note is that :class:`~contextvars_registry.context_var_descriptor.ContextVarDescriptor`
is NOT a subclass of :class:`~contextvars.ContextVar`. It should have been done a subclass,
but unfortunately, Python's :class:`~contextvars.ContextVar` cannot be subclassed (a technical limitation),
so :class:`~contextvars_registry.context_var_descriptor.ContextVarDescriptor`
is made a wrapper for :class:`~contextvars.ContextVar`.

If you really need to reach the lower-level :class:`~contextvars.ContextVar` object,
then you just use the ``.context_var`` attribute, like this::

    >>> CurrentVars.timezone.context_var
    <ContextVar name='__main__.CurrentVars.timezone'...>

But in most cases, you don't need it, because
:class:`~contextvars_registry.context_var_descriptor.ContextVarDescriptor` implements all the same
methods and attributes as the standard :class:`~contextvars.ContextVar`, so it should work
as a drop-in replacement in all cases except :func:`isinstance` checks.

In addition, :class:`ContextVarDescriptor` provides some extension methods
(not available in the standard :class:`~contextvars.ContextVar`)::

  >>> CurrentVars.timezone.is_set()
  True

  >>> CurrentVars.timezone.delete()

  >>> CurrentVars.timezone.is_set()
  False

The list of available methods can be found here: :doc:`context_var_descriptor`


Attribute Allocation
--------------------

As mentioned above, all registry attributes must be descriptors,
so when you set (or even just declare) an attribute, then :class:`ContextVarsRegistry`
automatically allocates a new :class:`~contextvars_registry.context_var_descriptor.ContextVarDescriptor`
for each attribute.

But, a little problem is that not all attributes should become context variables.
For example, you may want to define some methods in your registry subclass, and then
you probably expect methods to remain methods (not converted to context variables).

In most cases it automatically does the right thing, so you don't need to change anything,
but still, there are ways to alter automatic variable allocation, and there are special cases
that worth knowing about, so the section below describes the variable allocation procedure in detail.

There are 4 ways to allocate variables in a registry:

1. `by type annotation`_ (recommended)
2. `by value`_
3. `dynamic`_
4. `manual creation of ContextVarDescriptor()`_


by type annotation
~~~~~~~~~~~~~~~~~~

For attributes with type hints the rules are simple and explicit:

  * if you add :data:`~typing.ClassVar`, then attribute is skipped
  * otherwise it is converted to context variable

Example::

     >>> from typing import ClassVar

     >>> class CurrentVars(ContextVarsRegistry):
     ...     some_registry_setting: ClassVar[str] = "not a context variable"
     ...
     ...     user_id: int
     ...     timezone: str = "UTC"

     >>> CurrentVars.some_registry_setting
     'not a context variable'

     >>> CurrentVars.user_id
     <ContextVarDescriptor name='__main__.CurrentVars.user_id'>

     >>> CurrentVars.timezone
     <ContextVarDescriptor name='__main__.CurrentVars.timezone'>


Because rules for type annotations are so simple and explicit, this is the recommended way to go.


by value
~~~~~~~~

- Without type hints, things become a bit more complicated:

  * skipped:

    * methods (regular functions defined via ``def``)
    * :class:`@property` (and other kinds of descriptors)
    * special attributes (like :data:`__doc__`)

  * all other values are converted to context variables
    (including: :ref:`lambda`, :func:`~functools.partial` and custom :func:`callable` objects
    - they're all converted to context variables)

Example::

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

So, as you can see, without type annotations rules become somewhat magic,
sometimes even fragile. Like, for example, you may apply a decorator to your method,
and the decorator returns a :func:`~functools.partial` object, and then your method suddenly
becomes a :class:`ContextVarDescriptor`, which wasn't your intent.

To avoid such surprises, just use type hints. They make things safe and explicit.


dynamic
~~~~~~~

Registry automatically allocates new descriptors on the fly when setting attributes, check this out::

     >>> class CurrentVars(ContextVarsRegistry):
     ...     pass

     current = CurrentVars()

     current.timezone = "UTC"

     CurrentVars.timezone
     <ContextVarDescriptor name='__main__.CurrentVars.timezone'>


That means that you can start with an empty registry subclass, and then just set variables as needed.

This feature is akin to the famous `flask.g <https://flask.palletsprojects.com/en/2.1.x/appcontext/#storing-data>`_
object, where you set context-dependent global variables like this::

    from flask import g

    g.timezone = "UTC"


So now you can do a similar thing with pure context variables (not depending on Flask)::

    >>> class GlobalVars(ContextVarsRegistry):
    ...     pass

    >>> g = GlobalVars()

    >>> g.timezone = "UTC"


The dynamic allocation is on by default, but you can turn it off by overriding the
:attr:`ContextVarsRegistry._registry_allocate_on_setattr` attribute, like this::

    >>> class CurrentVars(ContextVarsRegistry):
    ...     _registry_allocate_on_setattr: ClassVar[bool] = False

    >>> current = CurrentVars()

    >>> current.timezone = "UTC"
    Traceback (most recent call last):
    ...
    AttributeError: 'CurrentVars' object has no attribute 'timezone'


manual creation of ContextVarDescriptor()
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can also just manually create :class:`ContextVarDescriptor` objects, like this::

     >>> from contextvars_registry import ContextVarDescriptor

     >>> class CurrentVars(ContextVarsRegistry):
     ...     timezone = ContextVarDescriptor(deferred_default=lambda: "UTC")

This is useful when you need to pass some extended constructor arguments,
like the :ref:`deferred_default <deferred-defaults>` in the example above.


``@property`` support
---------------------

:class:`ContextVarsRegistry` supports classic ``@property``, which is useful
for adding extra validation or data transformation when setting variables.

Here is an example of how ``@property`` can be used to validate timezone names,
and automatically convert them to :class:`datetime.tzinfo` objects using
`pytz <https://pythonhosted.org/pytz/>`_ package::

    >>> import pytz
    >>> from datetime import tzinfo

    >>> class CurrentVars(ContextVarsRegistry):
    ...     # a "private" context variable that stores the current timezone setting
    ...     _timezone: tzinfo = "UTC"
    ...
    ...     @property
    ...     def timezone(self):
    ...         return self._timezone
    ...
    ...     @timezone.setter
    ...     def timezone(self, new_timezone):
    ...         assert isinstance(new_timezone, tzinfo)
    ...         self._timezone = new_timezone
    ...
    ...     @timezone.deleter
    ...     def timezone(self):
    ...         del self._timezone
    ...
    ...     @property
    ...     def timezone_name(self):
    ...          return self._timezone.zone
    ...
    ...     @timezone_name.setter
    ...     def timezone_name(self, new_timezone_name):
    ...         assert isinstance(new_timezone_name, str)
    ...         self._timezone = pytz.timezone(new_timezone_name)
    ...
    ...     @timezone_name.deleter
    ...     def timezone_name(self):
    ...         del self._timezone

    >>> current = CurrentVars()

    >>> current.timezone_name = "GMT"

    >>> current.timezone
    <StaticTzInfo 'GMT'>


``with`` Syntax for Setting Attributes
--------------------------------------

:class:`ContextVarsRegistry` can act as a context manager, that allows you to
set attributes temporarily, like this::

    >>> class CurrentVars(ContextVarsRegistry):
    ...     locale: str =  "en"
    ...     timezone: str = "UTC"

    >>> current = CurrentVars()

    >>> with current(locale="en_GB", timezone="GMT"):
    ...     print(current.locale)
    ...     print(current.timezone)
    en_GB
    GMT

Upon exit from the ``with`` block, the attributes are reset to their previous values.

But, keep in mind that it doesn't restore state of the whole registry.
It is only a small syntax sugar over setting attributes, and it restores only attributes
that are listed inside the inside the ``with()`` parenthesizes, and nothing else.

If you need a full context isolation mechanism, then you should use tools from the
:mod:`~contextvars_registry.context_management` module.


Deleting Attributes
-------------------

In Python, it is not possible to delete a :class:`~contextvars.ContextVar` object.
(an attempt to do so causes a memory leak, so you shall never really delete context variables).

So, we have to do some trickery to implement deletion...

When you call ``del`` or :func:`delattr`, we don't actually delete anything,
but instead we write to the variable a special sentinel object called
:data:`~contextvars_registry.context_var_descriptor.DELETED`.

Later on, when the variable is read, there is a ``if`` check under the hood,
that detects the special sentinel object, and throws an exception.

On the high level, you should never notice this trick.
Attribute mechanics works like for a normal Python object,
as if its attribute was really deleted, check this out::

    >>> class CurrentVars(ContextVarsRegistry):
    ...    user_id: int = None

    >>> current =  CurrentVars()

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

The only case when you see this special :data:`~contextvars_registry.context_var_descriptor.DELETED` object
is when you use some low-level stuff, like :func:`save_context_vars_registry`, or
the :meth:`~.ContextVarDescriptor.get_raw` method::

    >>> CurrentVars.user_id.get_raw()
    <DELETED>

So, long story short: once a :class:`contextvars.ContextVar` object is allocated,
it lives forever in the registry.
When you delete it, we only mark it as deleted, but never actually delete it.
All this thing happens under the hood, and normally you shouln't notice it.


dict-like Access
----------------

:class:`ContextVarsRegistry` implements :class:`collections.abc.MutableMapping` protocol.

That means that you can get/set context variables, as if it was just a :class:`dict`, like this::

    >>> class CurrentVars(ContextVarsRegistry):
    ...    locale: str = 'en'
    ...    timezone: str = 'UTC'
    ...    user_id: int = None

    >>> current = CurrentVars()

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

    >>> list(current.keys())
    ['locale', 'timezone', 'user_id']

    >>> list(current.values())
    ['en', 'UTC', 42]

    >>> current.pop('locale')
    'en'

    >>> list(current.items())
    [('timezone', 'UTC'), ('user_id', 42)]



API reference
-------------

.. automodule:: contextvars_registry.context_vars_registry
   :special-members: __call__
   :private-members: _registry_allocate_on_setattr
