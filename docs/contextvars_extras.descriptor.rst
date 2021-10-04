contextvars\_extras.descriptor
==============================

.. currentmodule:: contextvars_extras.descriptor


:class:`ContextVarDescriptor` is an extended version the standard :class:`contextvars.ContextVar`.

It is not a sublass of :class:`~contextvars.ContextVar` (just because you cannot subclass it),
but a it is designed to be a fully compatible drop-in replacement of the :class:`~contextvars.ContextVar`.
That is, in most cases, you can just replace :class:`~contextvars.ContextVar`
with :class:`ContextVarDescriptor` in your code, and it would work as usual.

So, :class:`ContextVarDescriptor` implements all methods of the standard :class:`~contextvars.ContextVar`:

.. autosummary::

   ContextVarDescriptor.get
   ContextVarDescriptor.set
   ContextVarDescriptor.reset


plus, :class:`ContextVarDescriptor` has some extension methods:

.. autosummary::

   ContextVarDescriptor.is_set
   ContextVarDescriptor.set_if_not_set
   ContextVarDescriptor.reset_to_default
   ContextVarDescriptor.delete

and also, :class:`ContextVarDescriptor` has some extra features:

- `@property-like access`_ when you place it inside a class
- `deferred defaults`_ - use a function that produces a default value
- `value deletion`_ - erase variable (you cannot do that with standard Python's context vars)


ContextVarDescriptor creation
-----------------------------

There are 2 common ways to create a new :class:`ContextVarDescriptor` object:


standalone object
^^^^^^^^^^^^^^^^^

:class:`ContextVarDescriptor` can be used as a standalone object::

   >>> from contextvars_extras.descriptor import ContextVarDescriptor

   >>> locale_var = ContextVarDescriptor('locale_var', default='en')

   >>> locale_var.get()
   'en'

In this form, :class:`ContextVarDescriptor` behaves like a standard :class:`contextvars.ContextVar`,
but with extra methods and features.


class member
^^^^^^^^^^^^

A little bit more advanced form is to put it inside a class::

   >>> class MyVars:
   ...     locale = ContextVarDescriptor(default='en')


When placed inside a class, it has 2 advantages:

1. it behaves like a ``@property`` (see `@property-like access`_ section for details).
2. you don't have to come up with variable name, it is derived from class and attribute names.

Other than these 2 little things, there is no difference between standalone and class-member forms.
All other features should work in the exactly same way.

Also, :class:`ContextVarDescriptor` works best with :class:`~contextvars_extras.registry.ContextVarsRegistry`
(check out the :mod:`contextvars_extras.registry` documentation page), but, the registry class
is not strictly required, and :class:`ContextVarDescriptor` would work well within any other class.


@property-like access
---------------------

:class:`ContextVarDescriptor` is designed to be placed in a class attribute, like this::

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


Deferred Defaults
-----------------

Normally, you set a default value for a context variable like this::

  >>> locale_var = ContextVarDescriptor(
  ...     name='locale_var',
  ...     default='en'
  ... )

But, there is an alternative way: instead of a default value, you pass a function
that produces a default value, and pass it as the ``deferred_default`` argument::

  >>> locale_var = ContextVarDescriptor(
  ...     name='locale_var',
  ...     deferred_default=lambda: 'en'
  ... )

Then, the ``deferred_default()`` is postponed until the :meth:`ContextVarDescriptor.get` method
call, check this out::

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

``deferred_default`` is useful in several cases:

- The default value is not available yet.

  For example, the locale setting is stored in a configuration file, which is not yet parsed
  at the moment the context variable is created.

- The default value is expensive to get.

  Like, you have to download it from a remote storage.
  You probably don't want to do that at the moment the Python code is loaded.

- The default value is not thread-safe.

  Usually this is something like a "current HTTP session" (a `requests.Session`_ object),
  or maybe a "current DB session" (a `sqlalchemy.orm.Session`_ object), or something else
  that you don't want to share betwen threads/greenlets/coroutines.

  In this case, you set ``deferred_default`` to a function that creates ``Session`` objects,
  then if you spawn multiple threads, and then each thread will get its own ``Session`` instance.

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
Instead, it completely erases the variable. Even if ``default=...`` was set, it will
erase the default value, check this out::

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

If you want to reset variable to a default value, then you can use the special method:
:meth:`ContextVarDescriptor.reset_to_default`.

.. Note::

    Deletion is implemented in a bit hacky way
    (because in Python, you can't really erase a ContextVar object).

    When you call :meth:`~ContextVarDescriptor.delete`, a special marker object
    ``ContextVarValueDeleted`` is written into the context variable.

    Later on, :meth:`~ContextVarDescriptor.get` method detects the marker,
    and behaves as if there was no value.

    All this trickery happens under the hood, and normally you shouldn't notice it.
    However, it may appear if use the `underlying ContextVar object`_ directly,
    or call some performance-optimized methods, like :meth:`~ContextVarDescriptor.get_raw`::

        >>> timezone_var.get_raw()
        contextvars_extras.descriptor.ContextVarValueDeleted


underlying ContextVar object
----------------------------

When you create a new :class:`ContextVarDescriptor`, it automatically creates
a new :class:`~contexvars.ContextVar` object, which can be reached via the
:attr:`ContextVarDescriptor.context_var` attribute::

    >>> locale_var = ContextVarDescriptor('locale_var', default='en')

    >>> locale_var.context_var
    <ContextVar name='locale_var' default='en' ...>

Normally you don't want to use it (even for performance, see `Performance tips`_ section),
but in case you really want it, the ``.context_var`` attribute is there for you.

Also, it is possible to avoid auomatic creation of :class:`~contextvars.ContextVar` objects.
You can provide an existing object as the :class:`ContextVarDescriptor(context_var=...)` argument::

  >>> from contextvars import ContextVar

  # create a lower-level ContextVar object
  >>> locale_var = ContextVar('locale_var', default='en')

  # create a descriptor, passing the existing ContextVar as argument
  >>> locale_descriptor = ContextVarDescriptor(context_var=locale_var)

  # so then, .context_var attribute will be set to our existing ContextVar object
  >>> assert locale_descriptor.context_var is locale_var

  # and, .name is copied from ContextVar.name
  >>> locale_descriptor.name
  'locale_var'


Performance tips
----------------

One feature of Python's :mod:`contextvars` module is that it is written in C,
so you may expect low performance overhead out of the box.

The :class:`ContextVarDescriptor` is written in Python, so does it mean it is slow?
Do you need to switch to low-level :class:`~contextvars.ContextVar` when you need performance?

Well, yes, there is some overhead, but I (author of the code) try to keep it minimal.
I can't provide an extensive benchmark yet, but here is a very rough measurement from my local machine::

  >>> from timeit import timeit
  >>> from contextvars import ContextVar
  >>> from contextvars_extras.descriptor import ContextVarDescriptor

  >>> timezone_var = ContextVar('timezone_var', default='UTC')
  >>> timezone_descriptor = ContextVarDescriptor(context_var=timezone_var)

  # ContextVar.get() method call
  %timeit timezone_var.get()
  80.6 ns ± 1.43 ns per loop (mean ± std. dev. of 7 runs, 10000000 loops each)

  # ContextVarDescriptor.get() method call
  %timeit timezone_descriptor.get()
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
   <built-in method get of ContextVar ...>

   >>> locale_var.set
   <built-in method set of ContextVar ...>

   >>> locale_var.reset
   <built-in method reset of ContextVar ...>

That means that they have zero overhead, and if you use them,
you will get the same performance as the lower-level :class:`contextvars.ContextVar` implementation.


ContextVarDescriptor API reference
----------------------------------

.. automodule:: contextvars_extras.descriptor

   .. rubric:: ContextVarDescriptor

   .. autosummary::

      ContextVarDescriptor.__init__
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
