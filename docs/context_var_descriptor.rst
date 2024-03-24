module: context_var_descriptor
==============================

.. currentmodule:: contextvars_registry.context_var_descriptor

.. contents::

API Summary
-----------

.. rubric:: ContextVarDescriptor

.. autosummary::

   ContextVarDescriptor.context_var
   ContextVarDescriptor.name
   ContextVarDescriptor.default
   ContextVarDescriptor.deferred_default
   ContextVarDescriptor.__init__
   ContextVarDescriptor.from_existing_var
   ContextVarDescriptor.get
   ContextVarDescriptor.get_raw
   ContextVarDescriptor.is_gettable
   ContextVarDescriptor.is_set
   ContextVarDescriptor.set
   ContextVarDescriptor.set_if_not_set
   ContextVarDescriptor.reset
   ContextVarDescriptor.reset_to_default
   ContextVarDescriptor.delete


.. rubric:: Functions

.. autosummary::

   get_context_var_default


.. rubric:: Special objects

.. autosummary::

   NO_DEFAULT
   DELETED
   RESET_TO_DEFAULT


.. rubric:: Exceptions

.. autosummary::

   ContextVarNotSetError
   

class ContextVarDescriptor
--------------------------

:class:`ContextVarDescriptor` is a wrapper around the standard :class:`~contextvars.ContextVar` object,
that allows it to be placed in a class attribute, like this::

    >>> from contextvars_registry import ContextVarDescriptor

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

The underlying methods of :class:`~contextvars.ContextVar` (like :meth:`~contextvars.ContextVar.get()`
and :meth:`~contextvars.ContextVar.set()`) can be reached via class attributes::

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

In addition to standard methods, :class:`ContextVarDescriptor` provides some extension
methods (not available in the standard :class:`~contextvars.ContextVar`)::

  >>> MyVars.locale.delete()
  >>> MyVars.locale.get()
  Traceback (most recent call last):
  ...
  LookupError: <ContextVar ...>

  >>> MyVars.locale.reset_to_default()
  >>> MyVars.locale.get()
  'en'

  >>> MyVars.locale.is_set()
  False

  >>> MyVars.locale.set_if_not_set('en_US')
  'en_US'

  >>> MyVars.locale.get()
  'en_US'

see `API Summary`_ for the list of available methods.


Standalone Descriptor object
----------------------------

In case you don't like the ``@property`` magic, you can create :class:`ContextVarDescriptor` objects
outside of a class, and then it will behave like a standard :class:`~contextvars.ContextVar` object::

  >>> locale_var = ContextVarDescriptor('locale_var', default='en')

  # You can call the standard ContextVar.get()/.set()/.reset() methods
  >>> locale_var.get()
  'en'

  >>> token = locale_var.set('en_US')
  >>> token = locale_var.set('en_ZW')
  >>> locale_var.reset(token)
  >>> locale_var.get()
  'en_US'

  # ...and you can also use ContextVarDescriptor extensions:
  >>> locale_var.is_set()
  True

  >>> locale_var.default
  'en'

  >>> locale_var.reset_to_default()

  >>> locale_var.is_set()
  False

  >>> locale_var.get()
  'en'

.. Note::

  Although :class:`ContextVarDescriptor` is a drop-in replacement for :class:`~contextvars.ContextVar`,
  it is still NOT a subclass (just because :class:`~contextvars.ContextVar` doesn't allow
  any subclasses, this is a technical limitation of this built-in class).

  So, in terms of duck typing, :class:`ContextVarDescriptor` is fully compatible with
  :class:`~contextvars.ContextVar`, but :func:`isinstance` and static type checks would still fail.


Underlying ContextVar object
----------------------------

When you instantiate :class:`ContextVarDescriptor`, it automatically creates
a new :class:`~contexvars.ContextVar` object, which can be reached via the
:attr:`ContextVarDescriptor.context_var` attribute::

    >>> locale_var = ContextVarDescriptor('locale_var', default='en')

    >>> locale_var.context_var
    <ContextVar name='locale_var' default='en' ...>

Normally you don't want to use it (even for performance, see `Performance Tips`_ section),
but in case you really need it, the ``.context_var`` attribute is there for you.

Also, it is possible to avoid auomatic creation of :class:`~contextvars.ContextVar` objects,
and instead re-use an existing object via the alternative constructor method:
:meth:`ContextVarDescriptor.from_existing_var`::

  # create a lower-level ContextVar object
  >>> from contextvars import ContextVar
  >>> locale_var = ContextVar('locale_var', default='en')

  # create a ContextVarDescriptor() object, passing the existing ContextVar as argument
  >>> locale_var_descriptor = ContextVarDescriptor.from_existing_var(locale_var)

  # so then, .context_var attribute will be set to our existing ContextVar object
  >>> assert locale_var_descriptor.context_var is locale_var

  # and, .name is copied from ContextVar.name
  >>> locale_var_descriptor.name
  'locale_var'


.. _deferred-defaults:

Deferred Defaults
-----------------

Normally, you set a default value for a context variable like this::

  >>> locale_var = ContextVarDescriptor(
  ...     name='locale_var',
  ...     default='en'
  ... )

There is an alternative way: instead of a default value,
you pass :attr:`~ContextVarDescriptor.deferred_default` - a function that produces the default value,
like this::

  >>> locale_var = ContextVarDescriptor(
  ...     name='locale_var',
  ...     deferred_default=lambda: 'en'
  ... )

Then, the :attr:`~ContextVarDescriptor.deferred_default` is triggered by the first
call of the :meth:`ContextVarDescriptor.get` method, as shown in the example below::

  >>> def get_default_locale():
  ...     print('get_default_locale() was called')
  ...     return 'en'

  >>> locale_var = ContextVarDescriptor(
  ...     name='locale_var',
  ...     deferred_default=get_default_locale
  ... )

  >>> locale_var.get()
  get_default_locale() was called
  'en'

  # deferred_default is called once, and its result is stored in the variable
  # So, all subsequent .get() calls won't trigger get_default_locale()
  >>> locale_var.get()
  'en'

:attr:`~ContextVarDescriptor.deferred_default` is useful in several cases:

- The default value is not available yet.

  For example, the locale setting is stored in a configuration file, which is not yet parsed
  at the moment the context variable is created.

- The default value is expensive to get.

  Like, you have to download it from a remote storage.
  You probably don't want to do that at the moment the Python code is loaded.

- The default value is not thread-safe.

  Usually this is something like a "current HTTP session" (a `requests.Session`_ object),
  or maybe a "current DB session" (a `sqlalchemy.orm.Session`_ object), or something else
  that you don't want to share betwen threads/tasks/greenlets.

  In this case, you set :attr:`~ContextVarDescriptor.deferred_default` to a function
  that creates ``Session`` objects, and spawn multiple threads, and then each thread
  will get its own ``Session`` instance.

.. _requests.Session: https://docs.python-requests.org/en/master/user/advanced/#session-objects
.. _sqlalchemy.orm.Session: https://docs.sqlalchemy.org/en/14/orm/session.html


Value Deletion
--------------

Python's :mod:`contextvars` module has a limitation:
you cannot delete value stored in a :class:`~contextvars.ContextVar`.

The :class:`ContextVarDescriptor` fixes this limitation,
and provides :meth:`~ContextVarDescriptor.delete` method that allows to erase the variable,
like this::

    # Create a context variable, and set a value.
    >>> timezone_var = ContextVarDescriptor('timezone_var')
    >>> timezone_var.set('Europe/London')
    <Token ...>

    # ...so .get() call returns the value that we just set
    >>> timezone_var.get()
    'Europe/London'

    # Call .delete() to erase the value.
    >>> timezone_var.delete()

    # Once value is deleted, the .get() method raises LookupError.
    >>> try:
    ...     timezone_var.get()
    ... except LookupError:
    ...     print('LookupError was raised')
    LookupError was raised

    # The exception can be avoided by passing a `default=...` value.
    >>> timezone_var.get(default='GMT')
    'GMT'

Also note that a :meth:`~ContextVarDescriptor.delete()` call doesn't reset value to default.
Instead, it completely erases the variable. Even if ``default=...`` was set, it look
as if the default value was erased, check this out::

    >>> timezone_var = ContextVarDescriptor('timezone_var', default='UTC')

    # Before .delete() is called, .get() returns the `default=UTC`
    >>> timezone_var.get()
    'UTC'

    # Call .delete(). That erases the default value.
    >>> timezone_var.delete()

    # Now .get() will throw LookupError, as if there was no default value.
    >>> try:
    ...     timezone_var.get()
    ... except LookupError:
    ...     print('LookupError was raised')
    LookupError was raised

    # ...but you still can provide default as argument to ``.get()``
    >>> timezone_var.get(default='UTC')
    'UTC'

If you want to reset variable to the default value, then you can use :meth:`~ContextVarDescriptor.reset_to_default`.

.. Note::

    Python doesn't really allow to erase :class:`~contextvars.ContextVar`,
    so deletion is implemented in a hacky way:

    When you call :meth:`~ContextVarDescriptor.delete`, a special :data:`DELETED` object
    is written into the context variable.

    Later on, :meth:`~ContextVarDescriptor.get` method detects this special object,
    and behaves as if there was no value.

    All this trickery happens under the hood, and normally you shouldn't notice it.
    However, it may appear if use the `Underlying ContextVar object`_ directly,
    or call some performance-optimized methods, like :meth:`~ContextVarDescriptor.get_raw`::

        >>> timezone_var.get_raw()
        <DELETED>


Performance Tips
----------------

One feature of Python's :mod:`contextvars` module is that it is written in C,
so you may expect low performance overhead out of the box.

The :class:`ContextVarDescriptor` is written in Python, so does it mean it is slow?
Do you need to switch to low-level :class:`~contextvars.ContextVar` when you need performance?

Well, there is some overhead, but I (author of the code) try to keep it minimal.
I can't provide an extensive benchmark yet, but here is a very rough measurement from my local machine::

  >>> from timeit import timeit

  >>> timezone_var = ContextVar('timezone_var', default='UTC')
  >>> timezone_var_descriptor = ContextVarDescriptor.from_existing_var(timezone_var)

  # ContextVar.get() method call
  %timeit timezone_var.get()
  80.6 ns ± 1.43 ns per loop (mean ± std. dev. of 7 runs, 10000000 loops each)

  # ContextVarDescriptor.get() method call
  %timeit timezone_var_descriptor.get()
  220 ns ± 1.88 ns per loop (mean ± std. dev. of 7 runs, 1000000 loops each

  # cost of attribute lookup for comparison
  # (not calling the .get() method here, just measuring how expensive is a dot)
  %timeit ContextVarDescriptor.get
  34.3 ns ± 0.055 ns per loop (mean ± std. dev. of 7 runs, 10000000 loops each

Here :class:`ContextVarDescriptor` was ~3x slower than lower-level :class:`~contextvars.ContextVar`,
but, we're talking about **nanoseconds** overhead, which is quite good for Python code.

So the overhead is minor, but, if you still want to get rid of it,
There are 3 methods that point directly to low-level :class:`contextvars.ContextVar` implementation:

- :meth:`ContextVarDescriptor.get_raw` -> :meth:`contextvars.ContextVar.get`
- :meth:`ContextVarDescriptor.set` -> :meth:`contextvars.ContextVar.set`
- :meth:`ContextVarDescriptor.reset` -> :meth:`contextvars.ContextVar.reset`

These methods aren't wrappers. They're **direct references** to built-in methods, check this out::

   >>> locale_var = ContextVarDescriptor('locale_var')

   >>> locale_var.get_raw
   <built-in method get of ...ContextVar object ...>

   >>> locale_var.set
   <built-in method set of ...ContextVar object ...>

   >>> locale_var.reset
   <built-in method reset of ...ContextVar object ...>

That means that they have zero overhead, and if you use them,
you will get the same performance as the lower-level :class:`contextvars.ContextVar` implementation.



API reference
-------------

.. automodule:: contextvars_registry.context_var_descriptor
  :exclude-members: ContextVarDescriptor

  .. autoclass:: ContextVarDescriptor
    :special-members: __init__,__set_name__
    :inherited-members:
    :undoc-members:
