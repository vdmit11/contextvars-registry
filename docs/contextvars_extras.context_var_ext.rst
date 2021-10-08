ContextVarExt
=============

Overview
--------

.. currentmodule:: contextvars_extras.context_var_ext

:class:`ContextVarExt` is an extended version the standard :class:`contextvars.ContextVar`.

It is not a sublass of :class:`~contextvars.ContextVar` (just because you cannot subclass it),
but a it is designed to be a fully compatible drop-in replacement of the :class:`~contextvars.ContextVar`.

That is, in most cases, you can just replace :class:`~contextvars.ContextVar`
with :class:`ContextVarExt` in your code, and it would work as usual, check this out::

So, :class:`ContextVarExt` implements all methods of the standard :class:`~contextvars.ContextVar`:

.. autosummary::

   ContextVarExt.get
   ContextVarExt.set
   ContextVarExt.reset


plus, :class:`ContextVarExt` has some extension methods:

.. autosummary::

   ContextVarExt.is_set
   ContextVarExt.set_if_not_set
   ContextVarExt.reset_to_default
   ContextVarExt.delete

and also, :class:`ContextVarExt` it impplements some special features:

- `deferred defaults`_ - use a function that produces a default value
- `value deletion`_ - erase variable (you cannot do that with standard Python's context vars)


Deferred Defaults
-----------------

Normally, you set a default value for a context variable like this::

  >>> from contextvars_extras.context_var_ext import ContextVarExt

  >>> locale_var = ContextVarExt(
  ...     name='locale_var',
  ...     default='en'
  ... )

But, there is an alternative way: instead of a default value, you pass a function
that produces a default value, and pass it as the ``deferred_default`` argument::

  >>> locale_var = ContextVarExt(
  ...     name='locale_var',
  ...     deferred_default=lambda: 'en'
  ... )

Then, the ``deferred_default()`` is postponed until the :meth:`ContextVarExt.get` method
call, check this out::

  >>> def get_default_locale():
  ...     print('get_default_locale() was called')
  ...     return 'en'

  >>> locale_var = ContextVarExt(
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

The :class:`ContextVarExt` fixes this limitation,
and provides :meth:`~ContextVarExt.delete` method that allows to erase the variable,
like this::

    # Create a context variable, and set a value.
    >>> timezone_var = ContextVarExt('timezone_var')
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

Also note that a :meth:`~ContextVarExt.delete()` call doesn't reset value to default.
Instead, it completely erases the variable. Even if ``default=...`` was set, it will
erase the default value, check this out::

    >>> timezone_var = ContextVarExt('timezone_var', default='UTC')

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
:meth:`ContextVarExt.reset_to_default`.

.. Note::

    Deletion is implemented in a bit hacky way
    (because in Python, you can't really erase a ContextVar object).

    When you call :meth:`~ContextVarExt.delete`, a special marker object
    ``ContextVarValueDeleted`` is written into the context variable.

    Later on, :meth:`~ContextVarExt.get` method detects the marker,
    and behaves as if there was no value.

    All this trickery happens under the hood, and normally you shouldn't notice it.
    However, it may appear if use the `Underlying ContextVar object`_ directly,
    or call some performance-optimized methods, like :meth:`~ContextVarExt.get_raw`::

        >>> timezone_var.get_raw()
        contextvars_extras.context_var_ext.ContextVarValueDeleted


Underlying ContextVar object
----------------------------

When you create a new :class:`ContextVarExt`, it automatically creates
a new :class:`~contexvars.ContextVar` object, which can be reached via the
:attr:`ContextVarExt.context_var` attribute::

    >>> locale_var = ContextVarExt('locale_var', default='en')

    >>> locale_var.context_var
    <ContextVar name='locale_var' default='en' ...>

Normally you don't want to use it (even for performance, see `Performance Tips`_ section),
but in case you really want it, the ``.context_var`` attribute is there for you.

Also, it is possible to avoid auomatic creation of :class:`~contextvars.ContextVar` objects.
You can provide an existing object as the :class:`ContextVarExt(context_var=...)` argument::

  >>> from contextvars import ContextVar

  # create a lower-level ContextVar object
  >>> locale_var = ContextVar('locale_var', default='en')

  # create a descriptor, passing the existing ContextVar as argument
  >>> locale_descriptor = ContextVarExt(context_var=locale_var)

  # so then, .context_var attribute will be set to our existing ContextVar object
  >>> assert locale_descriptor.context_var is locale_var

  # and, .name is copied from ContextVar.name
  >>> locale_descriptor.name
  'locale_var'


Performance Tips
----------------

One feature of Python's :mod:`contextvars` module is that it is written in C,
so you may expect low performance overhead out of the box.

The :class:`ContextVarExt` is written in Python, so does it mean it is slow?
Do you need to switch to low-level :class:`~contextvars.ContextVar` when you need performance?

Well, yes, there is some overhead, but I (author of the code) try to keep it minimal.
I can't provide an extensive benchmark yet, but here is a very rough measurement from my local machine::

  >>> from timeit import timeit
  >>> from contextvars import ContextVar

  >>> timezone_var = ContextVar('timezone_var', default='UTC')
  >>> timezone_descriptor = ContextVarExt(context_var=timezone_var)

  # ContextVar.get() method call
  %timeit timezone_var.get()
  80.6 ns ± 1.43 ns per loop (mean ± std. dev. of 7 runs, 10000000 loops each)

  # ContextVarExt.get() method call
  %timeit timezone_descriptor.get()
  220 ns ± 1.88 ns per loop (mean ± std. dev. of 7 runs, 1000000 loops each

  # cost of attribute lookup for comparison
  # (not calling the .get() method here, just measuring how expensive is a dot)
  %timeit ContextVarExt.get
  34.3 ns ± 0.055 ns per loop (mean ± std. dev. of 7 runs, 10000000 loops each

Here :class:`ContextVarExt` was ~3x slower than lower-level :class:`~contextvars.ContextVar`,
but, we're talking about **nanoseconds** overhead, which is quite good for Python code.

So the overhead is minor, but, if you still want to get rid of it,
There are 3 methods that point directly to low-level :class:`contextvars.ContextVar` implementation:

- :meth:`ContextVarExt.get_raw` -> :meth:`contextvars.ContextVar.get`
- :meth:`ContextVarExt.set` -> :meth:`contextvars.ContextVar.set`
- :meth:`ContextVarExt.reset` -> :meth:`contextvars.ContextVar.reset`

These methods aren't wrappers. They're **direct references** to built-in methods, check this out::

   >>> locale_var = ContextVarExt('locale_var')

   >>> locale_var.get_raw
   <built-in method get of ContextVar ...>

   >>> locale_var.set
   <built-in method set of ContextVar ...>

   >>> locale_var.reset
   <built-in method reset of ContextVar ...>

That means that they have zero overhead, and if you use them,
you will get the same performance as the lower-level :class:`contextvars.ContextVar` implementation.


ContextVarExt API reference
---------------------------

.. automodule:: contextvars_extras.context_var_ext

   .. rubric:: ContextVarExt

   .. autosummary::

      ContextVarExt.__init__
      ContextVarExt.get
      ContextVarExt.get_raw
      ContextVarExt.is_set
      ContextVarExt.set
      ContextVarExt.set_if_not_set
      ContextVarExt.reset
      ContextVarExt.reset_to_default
      ContextVarExt.delete
