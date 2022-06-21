module: context_var_ext
=======================

This is documentation page for the module: :mod:`contextvars_extras.context_var_ext`

The module contains `class ContextVarExt`_, and its helpers.

.. contents:: Contents
   :local:

.. currentmodule:: contextvars_extras.context_var_ext

API summary
-----------

.. rubric:: `class ContextVarExt`_

.. autosummary::

   ContextVarExt.context_var
   ContextVarExt.name
   ContextVarExt.default
   ContextVarExt.deferred_default
   ContextVarExt.default_is_set
   ContextVarExt.__init__
   ContextVarExt.from_existing_var
   ContextVarExt.get
   ContextVarExt.get_raw
   ContextVarExt.is_gettable
   ContextVarExt.is_set
   ContextVarExt.set
   ContextVarExt.set_if_not_set
   ContextVarExt.reset
   ContextVarExt.reset_to_default
   ContextVarExt.delete

.. rubric:: Special objects

.. autosummary::

   NO_DEFAULT
   DELETED
   RESET_TO_DEFAULT

.. rubric:: Functions

.. autosummary::

   get_context_var_default


class ContextVarExt
-------------------

:class:`ContextVarExt` is an extended version of the standard :class:`contextvars.ContextVar`.

It is implemented as a wrapper (just because :class:`~contextvars.ContextVar` cannot be subclassed),
and it is designed to be backwards compatible with the standard :class:`~contextvars.ContextVar`,
at least in terms of `duck typing`_ (that is, :class:`ContextVarExt` implements all methods
and attributes of the :class:`~contextvars.ContextVar`).

.. _`duck typing`: https://docs.python.org/3/glossary.html#term-duck-typing

In most cases, you can just replace :class:`~contextvars.ContextVar`
with :class:`ContextVarExt` in your code, and it would work as usual.

That is, you just replace this::

  >>> from contextvars import ContextVar

  >>> locale_var = ContextVar('locale_var', default='en')

with this::

  >>> from contextvars_extras import ContextVarExt

  >>> locale_var = ContextVarExt('locale_var', default='en')

and then just continue using standard :class:`~contextvars.ContextVar` methods::

  >>> locale_var.get()
  'en'

  >>> token = locale_var.set('en_US')
  >>> locale_var.get()
  'en_US'

  >>> locale_var.reset(token)
  >>> locale_var.get()
  'en'

as well extended methods of :class:`ContextVarExt`
(not available in the standard :class:`~contextvars.ContextVar`)::

  >>> locale_var.delete()
  >>> locale_var.get()
  Traceback (most recent call last):
  ...
  LookupError: <ContextVar name='locale_var' ...>

  >>> locale_var.reset_to_default()
  >>> locale_var.get()
  'en'

  >>> locale_var.is_set()
  False

  >>> locale_var.set_if_not_set('en_US')
  'en_US'

  >>> locale_var.get()
  'en_US'

see `API Summary`_ for the list of available methods.


Underlying ContextVar object
----------------------------

When you instantiate :class:`ContextVarExt`, it automatically creates
a new :class:`~contexvars.ContextVar` object, which can be reached via the
:attr:`ContextVarExt.context_var` attribute::

    >>> locale_var = ContextVarExt('locale_var', default='en')

    >>> locale_var.context_var
    <ContextVar name='locale_var' default='en' ...>

Normally you don't want to use it (even for performance, see `Performance Tips`_ section),
but in case you really need it, the ``.context_var`` attribute is there for you.

Also, it is possible to avoid auomatic creation of :class:`~contextvars.ContextVar` objects,
and instead re-use an existing object via the alternative constructor method:
:meth:`ContextVarExt.from_existing_var`::

  # create a lower-level ContextVar object
  >>> locale_var = ContextVar('locale_var', default='en')

  # create a ContextVarExt() object, passing the existing ContextVar as argument
  >>> locale_var_ext = ContextVarExt.from_existing_var(locale_var)

  # so then, .context_var attribute will be set to our existing ContextVar object
  >>> assert locale_var_ext.context_var is locale_var

  # and, .name is copied from ContextVar.name
  >>> locale_var_ext.name
  'locale_var'


.. _deferred-defaults:

Deferred Defaults
-----------------

Normally, you set a default value for a context variable like this::

  >>> from contextvars_extras import ContextVarExt

  >>> locale_var = ContextVarExt(
  ...     name='locale_var',
  ...     default='en'
  ... )

There is an alternative way: instead of a default value,
you pass :attr:`~ContextVarExt.deferred_default` - a function that produces the default value,
like this::

  >>> locale_var = ContextVarExt(
  ...     name='locale_var',
  ...     deferred_default=lambda: 'en'
  ... )

Then, the :attr:`~ContextVarExt.deferred_default` is triggered by the first
call of the :meth:`ContextVarExt.get` method, as shown in the example below::

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

:attr:`~ContextVarExt.deferred_default` is useful in several cases:

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

  In this case, you set :attr:`~ContextVarExt.deferred_default` to a function
  that creates ``Session`` objects, and spawn multiple threads, and then each thread
  will get its own ``Session`` instance.

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
Instead, it completely erases the variable. Even if ``default=...`` was set, it look
as if the default value was erased, check this out::

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

If you want to reset variable to the default value, then you can use :meth:`~ContextVarExt.reset_to_default`.

.. Note::

    Python doesn't really allow to erase :class:`~contextvars.ContextVar`,
    so deletion is implemented in a hacky way:

    When you call :meth:`~ContextVarExt.delete`, a special :data:`DELETED` object
    is written into the context variable.

    Later on, :meth:`~ContextVarExt.get` method detects this special object,
    and behaves as if there was no value.

    All this trickery happens under the hood, and normally you shouldn't notice it.
    However, it may appear if use the `Underlying ContextVar object`_ directly,
    or call some performance-optimized methods, like :meth:`~ContextVarExt.get_raw`::

        >>> timezone_var.get_raw()
        <DELETED>


Performance Tips
----------------

One feature of Python's :mod:`contextvars` module is that it is written in C,
so you may expect low performance overhead out of the box.

The :class:`ContextVarExt` is written in Python, so does it mean it is slow?
Do you need to switch to low-level :class:`~contextvars.ContextVar` when you need performance?

Well, there is some overhead, but I (author of the code) try to keep it minimal.
I can't provide an extensive benchmark yet, but here is a very rough measurement from my local machine::

  >>> from timeit import timeit
  >>> from contextvars import ContextVar

  >>> timezone_var = ContextVar('timezone_var', default='UTC')
  >>> timezone_var_ext = ContextVarExt.from_existing_var(timezone_var)

  # ContextVar.get() method call
  %timeit timezone_var.get()
  80.6 ns ± 1.43 ns per loop (mean ± std. dev. of 7 runs, 10000000 loops each)

  # ContextVarExt.get() method call
  %timeit timezone_var_ext.get()
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
   <built-in method get of ...ContextVar object ...>

   >>> locale_var.set
   <built-in method set of ...ContextVar object ...>

   >>> locale_var.reset
   <built-in method reset of ...ContextVar object ...>

That means that they have zero overhead, and if you use them,
you will get the same performance as the lower-level :class:`contextvars.ContextVar` implementation.


API reference
-------------

.. automodule:: contextvars_extras.context_var_ext
   :exclude-members: ContextVarExt

   ..
      This autoclass below (in combination with :exclude-members above) is needed to make
      class ContextVarExt appear at the top of the documentation.

      That is, ContextVarExt is the most important thing in the module, so it should go first.

      It could be better to also place it at the top in the .py file, but this isn't possible,
      because ContextVarExt depends on NO_DEFAULT, so NO_DEFAULT has to go first in Python code.
      So, I had to do this :exclude-members: trick to change the order.

   .. autoclass:: ContextVarExt
